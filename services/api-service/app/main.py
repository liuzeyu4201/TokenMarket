"""API service with SF02 readiness, registration (SF03), and phone auth (SF04)."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.responses import Response

from . import database
from .api.v1.auth import router as auth_router
from .api.v1.authorization import router as authorization_router
from .api.v1.bindings import internal_router as bindings_internal_router
from .api.v1.bindings import router as bindings_router
from .api.v1.connections import internal_router as connections_internal_router
from .api.v1.connections import router as connections_router
from .api.v1.internal import router as internal_router
from .api.v1.project_keys import router as project_keys_router
from .api.v1.projects import router as projects_router
from .api.v1.proxy_keys import router as proxy_keys_router
from .api.v1.seller_keys import router as seller_keys_router
from .auth_rate_limit import MemoryAuthRateLimiter, build_auth_rate_limiter_from_env
from .config import clear_auth_settings_cache, load_auth_settings
from .dependencies import create_session_engine
from .dispatch.auth_delivery import AuthDeliveryDispatcher
from .domain.bindings.service import BindingService
from .domain.connections.health import FailClosedProbe, HealthService
from .domain.connections.lifecycle import BindingDependencies, LifecycleService
from .domain.connections.service import ConnectionService, ServiceConnectionLookup
from .domain.connections.store import MemoryConnectionStore
from .domain.endpcatalog import CatalogError, must_load
from .domain.projects.service import ProjectService
from .domain.proxykeys.service import ProxyKeyService
from .domain.sellerkeys.crypto import CredentialEncryptor
from .domain.sellerkeys.memory_store import MemoryKeyStore
from .domain.sellerkeys.validator_http import FailClosedValidator, GatewayValidator
from .domain.usage.service import UsageRecorder
from .errors import DependencyUnavailableError
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers
from .rate_limit import MemoryRateLimiter, build_rate_limiter_from_env
from .schemas.envelope import error_envelope
from .security.shared_secrets import SharedSecretError, load_process_shared_secrets
from .sms.synthetic import build_sms_adapter

VERSION = "0.1.0"
logger = configure_logging()


def _wire_key_services(application: FastAPI, database_url: str | None = None) -> None:
    """Attach seller/proxy/usage domain services used by SF08–SF17 HTTP."""
    try:
        material, fp, pepper, version, previous = load_process_shared_secrets()
    except SharedSecretError as exc:
        raise RuntimeError(f"shared crypto material rejected: {exc.message}") from exc
    validate_url = (os.environ.get("PROVIDER_VALIDATE_URL") or "").strip()
    validate_token = (os.environ.get("PROVIDER_VALIDATE_INTERNAL_TOKEN") or "").strip()
    if validate_url and validate_token:
        validator: GatewayValidator | FailClosedValidator = GatewayValidator(
            validate_url, validate_token
        )
    else:
        validator = FailClosedValidator()
    application.state.seller_encryptor = CredentialEncryptor(
        material, version, previous=previous
    )
    application.state.seller_fp_secret = fp
    application.state.seller_validator = validator
    application.state.seller_sync_engine = None
    store: Any = MemoryKeyStore()
    if database_url:
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from app.repositories.sessioned import (
                SessionedProxyStore,
                SessionedSQLKeyStore,
                SessionedUsageStore,
            )

            sync_url = database_url.replace("postgresql+asyncpg", "postgresql")
            engine = create_engine(sync_url, pool_pre_ping=True)
            application.state.seller_sync_engine = engine
            maker = sessionmaker(engine)
            store = SessionedSQLKeyStore(maker)
            application.state.usage_recorder = UsageRecorder(
                store=SessionedUsageStore(maker)
            )
            from app.repositories.bindings import SessionedBindingStore
            from app.repositories.connections import SessionedConnectionStore
            from app.repositories.projects import SessionedProjectStore

            proj_store = SessionedProjectStore(maker)
            bind_store = SessionedBindingStore(maker)
            conn_store = SessionedConnectionStore(maker)
            conn_svc = ConnectionService(
                application.state.seller_encryptor, fp, store=conn_store
            )
            bind_svc = BindingService(
                store=bind_store,
                projects=proj_store,
                connections=ServiceConnectionLookup(conn_svc),
            )
            conn_svc.bind_bindings(bind_svc)
            application.state.connection_service = conn_svc
            application.state.health_service = HealthService(
                conn_svc, FailClosedProbe()
            )
            application.state.lifecycle_service = LifecycleService(
                conn_svc, dependencies=BindingDependencies(bind_svc._store)
            )
            application.state.binding_service = bind_svc
            application.state.project_service = ProjectService(
                store=proj_store, binding=bind_svc
            )
            application.state.proxy_key_service = ProxyKeyService(
                pepper,
                store=SessionedProxyStore(maker),
                projects=proj_store,
                bindings=bind_svc,
            )
        except Exception:
            logger.warning("seller key SQL store disabled; using memory")
            from app.domain.projects.store import MemoryProjectStore

            mem_proj = MemoryProjectStore()
            conn_svc = ConnectionService(
                application.state.seller_encryptor, fp, store=MemoryConnectionStore()
            )
            bind_svc = BindingService(
                projects=mem_proj, connections=ServiceConnectionLookup(conn_svc)
            )
            conn_svc.bind_bindings(bind_svc)
            application.state.connection_service = conn_svc
            application.state.health_service = HealthService(
                conn_svc, FailClosedProbe()
            )
            application.state.lifecycle_service = LifecycleService(
                conn_svc, dependencies=BindingDependencies(bind_svc._store)
            )
            application.state.binding_service = bind_svc
            application.state.project_service = ProjectService(
                store=mem_proj, binding=bind_svc
            )
            application.state.proxy_key_service = ProxyKeyService(
                pepper, projects=mem_proj, bindings=bind_svc
            )
            application.state.usage_recorder = UsageRecorder()
    else:
        from app.domain.projects.store import MemoryProjectStore

        mem_proj = MemoryProjectStore()
        conn_svc = ConnectionService(
            application.state.seller_encryptor, fp, store=MemoryConnectionStore()
        )
        bind_svc = BindingService(
            projects=mem_proj, connections=ServiceConnectionLookup(conn_svc)
        )
        conn_svc.bind_bindings(bind_svc)
        application.state.connection_service = conn_svc
        application.state.health_service = HealthService(conn_svc, FailClosedProbe())
        application.state.lifecycle_service = LifecycleService(
            conn_svc, dependencies=BindingDependencies(bind_svc._store)
        )
        application.state.binding_service = bind_svc
        application.state.project_service = ProjectService(
            store=mem_proj, binding=bind_svc
        )
        application.state.proxy_key_service = ProxyKeyService(
            pepper, projects=mem_proj, bindings=bind_svc
        )
        application.state.usage_recorder = UsageRecorder()
    application.state.seller_key_store = store
    application.state.internal_token = os.environ.get("INTERNAL_GATEWAY_TOKEN") or ""


service_info = Info("app", "API service build information")
service_info.info({"service": "api-service", "version": VERSION})

_AUTH_PATH_PREFIX = "/api/v1/auth"
_CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
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
    try:
        catalog = must_load()
    except CatalogError as exc:
        logger.error(
            "endpoint catalog load failed",
            extra={"code": exc.code, "message": exc.message},
        )
        raise
    app.state.endpoint_catalog = catalog
    logger.info(
        "endpoint catalog loaded",
        extra={
            "catalog_major": catalog["catalog_major"],
            "catalog_minor": catalog["catalog_minor"],
            "freeze_date": catalog["freeze_date"],
            "record_count": len(catalog["records"]),
        },
    )
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
    _wire_key_services(app, database_url if session_factory is not None else None)

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
    sync_engine = getattr(app.state, "seller_sync_engine", None)
    if sync_engine is not None:
        sync_engine.dispose()


app = FastAPI(title="TokenMarket API Service", version=VERSION, lifespan=lifespan)
app.state.version = VERSION
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(authorization_router)
app.include_router(seller_keys_router)
app.include_router(proxy_keys_router)
app.include_router(projects_router)
app.include_router(project_keys_router)
app.include_router(bindings_router)
app.include_router(bindings_internal_router)
app.include_router(connections_router)
app.include_router(connections_internal_router)
app.include_router(internal_router)

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
