"""API service with SF02 readiness and user registration (SF03)."""

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
from .dependencies import create_session_engine
from .errors import DependencyUnavailableError
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers
from .rate_limit import MemoryRateLimiter, build_rate_limiter_from_env
from .schemas.envelope import error_envelope

VERSION = "0.1.0"
logger = configure_logging()

service_info = Info("app", "API service build information")
service_info.info({"service": "api-service", "version": VERSION})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own readiness engine, session factory, and rate limiter for the process."""
    engine: AsyncEngine | None = None
    session_engine: AsyncEngine | None = None
    rate_limiter = build_rate_limiter_from_env()
    if rate_limiter is None:
        rate_limiter = MemoryRateLimiter(fail=True)
        logger.warning("REDIS_URL not set; registration rate limiter fail-closed")

    database_url = os.environ.get("DATABASE_URL")
    app.state.session_factory = None
    if database_url is not None:
        try:
            engine = database.create_readiness_engine(database_url)
            session_engine = create_session_engine(database_url)
            app.state.session_factory = async_sessionmaker(
                session_engine, class_=AsyncSession, expire_on_commit=False
            )
        except Exception:
            logger.warning("database readiness probe disabled: invalid config")
            engine = None
            app.state.session_factory = None

    app.state.db_engine = engine
    app.state.readiness_probe = database.build_readiness_probe(engine)
    app.state.rate_limiter = rate_limiter
    yield
    await rate_limiter.close()
    if session_engine is not None:
        await session_engine.dispose()
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="TokenMarket API Service", version=VERSION, lifespan=lifespan)
app.state.version = VERSION
app.include_router(health_router)
app.include_router(auth_router)

_cors_origins = os.environ.get(
    "CORS_ALLOW_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
