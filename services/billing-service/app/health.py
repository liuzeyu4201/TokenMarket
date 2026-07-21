"""Health endpoints for the Billing service (SF01 liveness + SF02 readiness)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .database import ProbeErrorCategory, ProbeOutcome
from .observability import record_postgres_readiness_probe

router = APIRouter()

_SERVICE = "billing-service"


def _response(request: Request, status: str) -> dict[str, str]:
    return {
        "service": _SERVICE,
        "status": status,
        "version": request.app.state.version,
        "request_id": request.state.request_id,
    }


@router.get("/health/live")
async def liveness(request: Request) -> dict[str, str]:
    return _response(request, "alive")


@router.get("/health/ready", response_model=None)
async def readiness(request: Request) -> dict[str, Any] | JSONResponse:
    """Run one fresh bounded PostgreSQL probe per request.

    Success keeps the unchanged SF01 200 shape. Failure returns only the
    contracted 503 dependency shape naming ``postgres`` with a stable safe
    code; probe errors never reach the response.
    """
    probe = getattr(request.app.state, "postgres_probe", None)
    start = time.monotonic()
    if probe is None:
        outcome = ProbeOutcome(ok=False, category=ProbeErrorCategory.INVALID_CONFIG)
    else:
        try:
            outcome = await probe()
        except Exception:
            # A readiness signal must never 500 or leak probe internals.
            outcome = ProbeOutcome(ok=False, category=ProbeErrorCategory.UNAVAILABLE)
    duration = time.monotonic() - start
    record_postgres_readiness_probe(ok=outcome.ok, duration_seconds=duration)
    if outcome.ok:
        return _response(request, "ready")
    code = (
        "INVALID_CONFIG"
        if outcome.category is ProbeErrorCategory.INVALID_CONFIG
        else "DEPENDENCY_NOT_READY"
    )
    payload: dict[str, Any] = {
        "service": _SERVICE,
        "status": "not_ready",
        "version": request.app.state.version,
        "request_id": request.state.request_id,
        "dependencies": [{"name": "postgres", "status": "not_ready", "code": code}],
    }
    return JSONResponse(status_code=503, content=payload)
