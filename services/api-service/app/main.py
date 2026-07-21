"""API service SF01 scaffold with SF02 PostgreSQL-aware readiness."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.responses import Response

from . import database
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers

VERSION = "0.1.0"
logger = configure_logging()

service_info = Info("app", "API service build information")
service_info.info({"service": "api-service", "version": VERSION})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the readiness engine and probe for the process lifetime.

    The engine is created once on startup and disposed on shutdown. Absent
    or invalid configuration never crashes the process: liveness stays
    independent, and readiness reports the stable invalid-config category
    until configuration and PostgreSQL both allow a successful probe.
    """
    engine: AsyncEngine | None = None
    database_url = os.environ.get("DATABASE_URL")
    if database_url is not None:
        try:
            engine = database.create_readiness_engine(database_url)
        except database.InvalidConfigError:
            logger.warning("database readiness probe disabled: invalid config")
            engine = None
    app.state.db_engine = engine
    app.state.readiness_probe = database.build_readiness_probe(engine)
    yield
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="TokenMarket API Service", version=VERSION, lifespan=lifespan)
app.state.version = VERSION
app.include_router(health_router)


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
