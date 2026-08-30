"""Admin service SF01 scaffold."""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest
from starlette.responses import Response

from .domain.endpcatalog import CatalogError, must_load
from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers

VERSION = "0.1.0"
logger = configure_logging()

try:
    _catalog = must_load()
except CatalogError as exc:
    logger.error(
        "endpoint catalog load failed",
        extra={"code": exc.code, "message": exc.message},
    )
    raise
logger.info(
    "endpoint catalog loaded",
    extra={
        "catalog_major": _catalog["catalog_major"],
        "catalog_minor": _catalog["catalog_minor"],
        "freeze_date": _catalog["freeze_date"],
        "record_count": len(_catalog["records"]),
    },
)

service_info = Info("app", "Admin service build information")
service_info.info({"service": "admin-service", "version": VERSION})

app = FastAPI(title="TokenMarket Admin Service", version=VERSION)
app.state.version = VERSION
app.state.endpoint_catalog = _catalog
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
            "service": "admin-service",
            "status": "not_found",
            "version": getattr(request.app.state, "version", VERSION),
            "request_id": getattr(request.state, "request_id", generate_request_id()),
        },
    )
