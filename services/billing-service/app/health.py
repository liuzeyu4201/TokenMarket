"""Health endpoints for the Billing service scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


def _response(request: Request, status: str) -> dict[str, str]:
    return {
        "service": "billing-service",
        "status": status,
        "version": request.app.state.version,
        "request_id": request.state.request_id,
    }


@router.get("/health/live")
async def liveness(request: Request) -> dict[str, str]:
    return _response(request, "alive")


@router.get("/health/ready")
async def readiness(request: Request) -> dict[str, str]:
    return _response(request, "ready")
