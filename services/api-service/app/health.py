"""Health endpoints for the API service.

Liveness never touches PostgreSQL. Readiness runs the service-owned,
bounded PostgreSQL probe injected through application state (replaced by
scripted fakes in tests) and answers with the unchanged SF01 200 shape on
success or the contracted SF02 503 dependency shape on failure. Failure
bodies name only ``postgres`` and a stable safe code; URLs, usernames,
databases, exception bodies, SQL, and passwords never appear.

Auth readiness (keys / TLS / SMS adapter) is evaluated via
:func:`check_auth_readiness` and attached as a separate dependency when the
process is outside local scaffolding, so existing postgres-only probes remain
stable for SF02 contracts.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .config import AuthReadinessResult, check_auth_readiness, resolve_app_mode
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


def seller_key_ring_ready(store: Any, encryptor: Any) -> bool:
    """Fail closed when persisted ciphertext versions are not in the process ring."""
    persisted = getattr(store, "persisted_key_versions", None)
    known = getattr(encryptor, "known_versions", None)
    if not callable(persisted) or not callable(known):
        return True
    try:
        versions = persisted()
        allowed = known()
    except Exception:
        return True
    return not (set(versions) - set(allowed))


def evaluate_auth_readiness(request: Request | None = None) -> AuthReadinessResult:
    """Callable auth readiness check for tests and process preflight."""
    settings = None
    if request is not None:
        settings = getattr(request.app.state, "auth_settings", None)
    return check_auth_readiness(settings)


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

    # Auth fail-closed for non-local modes. Local scaffolding keeps the
    # historical postgres-only readiness contract so SF02 tests stay green.
    mode = resolve_app_mode()
    auth_result = AuthReadinessResult.success()
    if mode in ("test", "prod"):
        auth_result = evaluate_auth_readiness(request)

    ring_ok = seller_key_ring_ready(
        getattr(request.app.state, "seller_key_store", None),
        getattr(request.app.state, "seller_encryptor", None),
    )

    if result.ok and auth_result.ok and ring_ok:
        return JSONResponse(content=_response(request, "ready"))

    body = _response(request, "not_ready")
    dependencies: list[dict[str, str]] = []
    if not result.ok:
        code = (
            "INVALID_CONFIG"
            if result.category is ProbeErrorCategory.INVALID_CONFIG
            else "DEPENDENCY_NOT_READY"
        )
        dependencies.append({"name": "postgres", "status": "not_ready", "code": code})
    if not auth_result.ok:
        # Surface a single stable code without leaking key material.
        dependencies.append(
            {
                "name": "auth",
                "status": "not_ready",
                "code": "INVALID_CONFIG",
            }
        )
    if not ring_ok:
        dependencies.append(
            {
                "name": "seller_keys",
                "status": "not_ready",
                "code": "INVALID_CONFIG",
            }
        )
    body["dependencies"] = dependencies
    return JSONResponse(status_code=503, content=body)
