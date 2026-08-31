"""Billing service SF01 scaffold with SF02 PostgreSQL-aware readiness."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine

from .api.ledger import router as ledger_router
from .api.recon import router as recon_router
from .database import (
    InvalidDatabaseConfigError,
    ProbeErrorCategory,
    ProbeOutcome,
    ReadinessProbe,
    create_postgres_engine,
    probe_postgres_readiness,
)
from .domain.endpcatalog import CatalogError, must_load
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers

VERSION = "0.1.0"
logger = configure_logging()

service_info = Info("app", "Billing service build information")
service_info.info({"service": "billing-service", "version": VERSION})


async def _invalid_config_probe() -> ProbeOutcome:
    return ProbeOutcome(ok=False, category=ProbeErrorCategory.INVALID_CONFIG)


def _build_probe_from_env() -> tuple[ReadinessProbe, AsyncEngine | None]:
    """Build the lifespan-owned probe from DATABASE_URL, failing closed.

    Invalid configuration never raises and never echoes the URL; readiness
    reports INVALID_CONFIG while liveness stays independent.
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        return _invalid_config_probe, None
    try:
        engine = create_postgres_engine(database_url)
    except InvalidDatabaseConfigError:
        logger.warning("postgres readiness probe disabled: invalid configuration")
        return _invalid_config_probe, None

    async def _probe() -> ProbeOutcome:
        return await probe_postgres_readiness(engine)

    return _probe, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the probe engine: create on startup, dispose on shutdown.

    Tests may inject ``app.state.postgres_probe``/``postgres_engine`` before
    startup; injected probes are preserved while any present engine is still
    disposed at shutdown.
    """
    try:
        catalog = must_load()
    except CatalogError as exc:
        logger.error(
            "endpoint catalog load failed",
            extra={"code": exc.code, "detail": exc.message},
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
    created = getattr(app.state, "postgres_probe", None) is None
    if created:
        probe, engine = _build_probe_from_env()
        app.state.postgres_probe = probe
        app.state.postgres_engine = engine
    yield
    engine = getattr(app.state, "postgres_engine", None)
    if engine is not None:
        await engine.dispose()
    app.state.postgres_engine = None
    if created:
        app.state.postgres_probe = None


app = FastAPI(title="TokenMarket Billing Service", version=VERSION, lifespan=lifespan)
app.state.version = VERSION
app.include_router(health_router)
app.include_router(ledger_router)
app.include_router(recon_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
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
async def metrics():
    return generate_latest()


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "service": "billing-service",
            "status": "not_found",
            "version": getattr(request.app.state, "version", VERSION),
            "request_id": getattr(request.state, "request_id", generate_request_id()),
        },
    )
