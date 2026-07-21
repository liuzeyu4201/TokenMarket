"""Health endpoints for the API service.

Liveness never touches PostgreSQL. Readiness runs the service-owned,
bounded PostgreSQL probe injected through application state (replaced by
scripted fakes in tests) and answers with the unchanged SF01 200 shape on
success or the contracted SF02 503 dependency shape on failure. Failure
bodies name only ``postgres`` and a stable safe code; URLs, usernames,
databases, exception bodies, SQL, and passwords never appear.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .database import ProbeCallable, ProbeErrorCategory, ProbeResult
from .observability import record_readiness_probe

router = APIRouter()


def _response(request: Request, status: str) -> dict[str, Any]:
    return {
        "service": "api-service",
        "status": status,
        "version": request.app.state.version,
        "request_id": request.state.request_id,
    }


@router.get("/health/live")
async def liveness(request: Request) -> dict[str, Any]:
    return _response(request, "alive")


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    probe: ProbeCallable = request.app.state.readiness_probe
    started = time.monotonic()
    try:
        result = await probe()
    except Exception:  # a broken probe is still a safe not-ready answer
        result = ProbeResult.failure(ProbeErrorCategory.UNAVAILABLE)
    record_readiness_probe(result.ok, time.monotonic() - started)
    if result.ok:
        return JSONResponse(content=_response(request, "ready"))
    code = (
        "INVALID_CONFIG"
        if result.category is ProbeErrorCategory.INVALID_CONFIG
        else "DEPENDENCY_NOT_READY"
    )
    body = _response(request, "not_ready")
    body["dependencies"] = [{"name": "postgres", "status": "not_ready", "code": code}]
    return JSONResponse(status_code=503, content=body)
