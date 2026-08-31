"""Admin identity HTTP. Prefix /admin/v1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.domain.admin import ADMIN_COOKIE, USER_COOKIE, AdminError, AdminService

router = APIRouter(prefix="/admin/v1", tags=["admin"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str
    password: str
    mfa_code: str = ""


class StepUpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mfa_code: str


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    target: str
    reason: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class CloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review: str


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


def _svc(request: Request) -> AdminService:
    svc = getattr(request.app.state, "admin_service", None)
    if not isinstance(svc, AdminService):
        svc = AdminService()
        request.app.state.admin_service = svc
    return svc


def _fail(exc: AdminError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_envelope(exc.code, exc.message, rid),
    )


def _tokens(request: Request) -> tuple[str | None, str | None]:
    admin = request.cookies.get(ADMIN_COOKIE)
    user = request.cookies.get(USER_COOKIE)
    return admin, user


@router.post("/sessions")
async def login(body: LoginBody, request: Request, response: Response) -> JSONResponse:
    rid = _rid(request)
    _, user = _tokens(request)
    try:
        sess, token = _svc(request).login(
            login=body.login,
            password=body.password,
            mfa_code=body.mfa_code,
            user_cookie=user,
        )
    except AdminError as exc:
        return _fail(exc, rid)
    response = JSONResponse(
        status_code=200,
        content=_envelope("0", "ok", rid, {"admin_id": sess.admin_id, "role": "admin"}),
    )
    # Header carries the isolated cookie name; TestClient may drop __Host- flags.
    response.headers["Set-Cookie"] = _svc(request).cookie_header(token)
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        path="/admin",
        httponly=True,
        samesite="strict",
        max_age=3600,
    )
    return response


@router.post("/step-up")
async def step_up(body: StepUpBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    admin, user = _tokens(request)
    try:
        _svc(request).resolve(admin_token=admin, user_cookie=user)
        _svc(request).step_up(admin_token=admin or "", mfa_code=body.mfa_code)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"stepped": True})
    )


@router.post("/actions")
async def actions(body: ActionBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    admin, user = _tokens(request)
    try:
        out = _svc(request).execute(
            admin_token=admin,
            user_cookie=user,
            action=body.action,
            target=body.target,
            reason=body.reason,
            request_id=rid,
            before=body.before,
            after=body.after,
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, out))


@router.get("/audit")
async def list_audit(request: Request) -> JSONResponse:
    rid = _rid(request)
    admin, user = _tokens(request)
    try:
        acc = _svc(request).resolve(admin_token=admin, user_cookie=user)
        if not (acc.role in {"security_audit", "support"}):
            raise AdminError("FORBIDDEN", "当前角色无权执行该操作", http_status=403)
    except AdminError as exc:
        return _fail(exc, rid)
    items = [
        {
            "event_id": r.event_id,
            "actor_id": r.actor_id,
            "action": r.action,
            "result": r.result,
            "record_hash": r.record_hash,
        }
        for r in _svc(request).audit.list()
    ]
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"items": items})
    )


@router.post("/break-glass/{case_id}/close")
async def close_bg(case_id: str, body: CloseBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    admin, user = _tokens(request)
    try:
        _svc(request).resolve(admin_token=admin, user_cookie=user)
        case = _svc(request).close_break_glass(
            admin_token=admin or "", case_id=case_id, review=body.review
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=_envelope("0", "ok", rid, {"closed": case.closed_at is not None}),
    )
