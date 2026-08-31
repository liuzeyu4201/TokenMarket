"""SLO and alert HTTP. Prefix /admin/v1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.domain.admin import ADMIN_COOKIE, USER_COOKIE, AdminError, AdminService
from app.domain.admin.rbac import evaluate
from app.domain.slo.alerts import evaluate_alert
from app.domain.slo.budget import snapshot
from app.domain.slo.trace import TraceLog

router = APIRouter(prefix="/admin/v1", tags=["slo"])


class EvalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    sample: dict[str, float | int]


class SLOStore:
    def __init__(self) -> None:
        self.trace = TraceLog()
        self.samples = {
            "dataplane": {"good": 9990, "total": 10000},
            "admin": {"good": 9990, "total": 10000},
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(code: str, message: str, rid: str, data: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": rid,
        "timestamp": _now(),
    }


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _fail(exc: AdminError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_envelope(exc.code, exc.message, rid),
    )


def _admin(request: Request) -> AdminService:
    svc = getattr(request.app.state, "admin_service", None)
    if not isinstance(svc, AdminService):
        svc = AdminService()
        request.app.state.admin_service = svc
    return svc


def _store(request: Request) -> SLOStore:
    store = getattr(request.app.state, "slo_store", None)
    if not isinstance(store, SLOStore):
        store = SLOStore()
        request.app.state.slo_store = store
    return store


def _require_alert_read(request: Request) -> None:
    admin = request.cookies.get(ADMIN_COOKIE)
    user = request.cookies.get(USER_COOKIE)
    acc = _admin(request).resolve(admin_token=admin, user_cookie=user)
    if not evaluate(acc.role, acc.readonly, "alert.read"):
        raise AdminError("FORBIDDEN", "当前角色无权执行该操作", http_status=403)


@router.get("/slo")
async def get_slo(request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        _require_alert_read(request)
        store = _store(request)
        data = {
            plane: snapshot(
                plane=plane, good=vals["good"], total=vals["total"]
            ).as_dict()
            for plane, vals in store.samples.items()
        }
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, data))


@router.get("/slo/traces/{request_id}")
async def get_trace(request_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        _require_alert_read(request)
        hops = [h.as_dict() for h in _store(request).trace.correlate(request_id)]
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"hops": hops})
    )


@router.post("/slo/alerts/evaluate")
async def eval_alert(body: EvalBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        _require_alert_read(request)
        inst = evaluate_alert(body.kind, body.sample)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, inst.as_dict())
    )
