"""API service with SF02 readiness, registration (SF03), and phone auth (SF04)."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.responses import Response

from . import database
from .api.v1.auth import router as auth_router
from .api.v1.authorization import router as authorization_router
from .auth_rate_limit import MemoryAuthRateLimiter, build_auth_rate_limiter_from_env
from .config import clear_auth_settings_cache, load_auth_settings
from .dependencies import create_session_engine
from .dispatch.auth_delivery import AuthDeliveryDispatcher
from .errors import DependencyUnavailableError
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers
from .rate_limit import MemoryRateLimiter, build_rate_limiter_from_env
from .schemas.envelope import error_envelope
from .sms.synthetic import build_sms_adapter

VERSION = "0.1.0"
logger = configure_logging()

service_info = Info("app", "API service build information")
service_info.info({"service": "api-service", "version": VERSION})

_AUTH_PATH_PREFIX = "/api/v1/auth"
_CORS_ALLOW_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]
_CORS_ALLOW_HEADERS = [
    "Content-Type",
    "X-Request-ID",
    "Idempotency-Key",
    "X-CSRF-Token",
]


def _browser_origins() -> list[str]:
    """Exact browser Origin allowlist from AUTH_BROWSER_ORIGINS (no wildcards)."""
    clear_auth_settings_cache()
    try:
        settings = load_auth_settings()
        origins = settings.browser_origin_list
    except Exception:
        origins = []
    if origins:
        return origins
    # Backward-compatible local default for SF03 registration UI.
    legacy = os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,"
        "https://127.0.0.1:5173,https://localhost:5173",
    )
    return [o.strip() for o in legacy.split(",") if o.strip() and o.strip() != "*"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own readiness engine, session factory, rate limiter, and auth dispatcher."""
    engine: AsyncEngine | None = None
    session_engine: AsyncEngine | None = None
    dispatcher: AuthDeliveryDispatcher | None = None
    rate_limiter = build_rate_limiter_from_env()
    if rate_limiter is None:
        rate_limiter = MemoryRateLimiter(fail=True)
        logger.warning("REDIS_URL not set; registration rate limiter fail-closed")

    auth_rate_limiter = build_auth_rate_limiter_from_env()
    if auth_rate_limiter is None:
        auth_rate_limiter = MemoryAuthRateLimiter(fail=True)
        logger.warning("REDIS_URL not set; auth rate limiter fail-closed")

    clear_auth_settings_cache()
    try:
        auth_settings = load_auth_settings()
    except Exception:
        logger.warning("auth settings load failed; using empty defaults")
        from .config import AuthSettings

        auth_settings = AuthSettings()
    app.state.auth_settings = auth_settings

    # SMS adapter (tests may replace app.state.sms_adapter before requests).
    override = getattr(app.state, "sms_adapter_override", None)
    sms_adapter = build_sms_adapter(auth_settings, override=override)
    app.state.sms_adapter = sms_adapter

    database_url = os.environ.get("DATABASE_URL")
    session_factory: async_sessionmaker[AsyncSession] | None = None
    app.state.session_factory = None
    if database_url is not None:
        try:
            engine = database.create_readiness_engine(database_url)
            session_engine = create_session_engine(database_url)
            session_factory = async_sessionmaker(
                session_engine, class_=AsyncSession, expire_on_commit=False
            )
            app.state.session_factory = session_factory
        except Exception:
            logger.warning("database readiness probe disabled: invalid config")
            engine = None
            session_factory = None
            app.state.session_factory = None

    app.state.db_engine = engine
    app.state.readiness_probe = database.build_readiness_probe(engine)
    app.state.rate_limiter = rate_limiter
    app.state.auth_rate_limiter = auth_rate_limiter

    # Start delivery dispatcher when DB + keys are usable (local/test).
    # Inline ``session_factory is not None`` so mypy narrows the factory type.
    if (
        os.environ.get("AUTH_DISPATCHER_ENABLED", "1") != "0"
        and session_factory is not None
        and auth_settings.key_material("otp").current_usable()
    ):
        dispatcher = AuthDeliveryDispatcher(
            session_factory,
            auth_settings,
            sms_adapter,  # type: ignore[arg-type]
        )
        app.state.auth_dispatcher = dispatcher
        dispatcher.start()
    else:
        app.state.auth_dispatcher = None

    yield

    if dispatcher is not None:
        await dispatcher.stop()
    await rate_limiter.close()
    await auth_rate_limiter.close()
    if session_engine is not None:
        await session_engine.dispose()
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="TokenMarket API Service", version=VERSION, lifespan=lifespan)
app.state.version = VERSION
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(authorization_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_browser_origins(),
    allow_credentials=True,
    allow_methods=_CORS_ALLOW_METHODS,
    allow_headers=_CORS_ALLOW_HEADERS,
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    rid = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
    if not rid:
        rid = generate_request_id()
    request.state.request_id = rid

    logger.info(
        "request start",
        extra={
            "method": request.method,
            "path": request.url.path,
            "request_id": rid,
            "headers": redact_headers(dict(request.headers)),
        },
    )

    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid

    # Auth and session responses must never be cached by browsers or proxies.
    if request.url.path.startswith(_AUTH_PATH_PREFIX):
        response.headers["Cache-Control"] = "no-store"

    logger.info(
        "request end",
        extra={
            "request_id": rid,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "status_code": response.status_code,
        },
    )
    return response


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> bytes:
    return generate_latest()


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "service": "api-service",
            "status": "not_found",
            "version": getattr(request.app.state, "version", VERSION),
            "request_id": getattr(request.state, "request_id", generate_request_id()),
        },
    )


@app.exception_handler(DependencyUnavailableError)
async def dependency_unavailable_handler(
    request: Request, exc: DependencyUnavailableError
) -> JSONResponse:
    """FR-009: dependency failures use the unified business envelope."""
    rid = getattr(request.state, "request_id", generate_request_id())
    return JSONResponse(
        status_code=503,
        content=error_envelope(exc.code, exc.message, request_id=rid),
    )
