"""Billing service SF01 scaffold."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Info, generate_latest

from .health import router as health_router
from .observability import configure_logging, generate_request_id, redact_headers

VERSION = "0.1.0"
logger = configure_logging()

service_info = Info("app", "Billing service build information")
service_info.info({"service": "billing-service", "version": VERSION})

app = FastAPI(title="TokenMarket Billing Service", version=VERSION)
app.state.version = VERSION
app.include_router(health_router)


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
