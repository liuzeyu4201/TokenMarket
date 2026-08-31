"""Ops catalog, config pipeline, and wizard HTTP. Prefix /admin/v1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.domain.admin import ADMIN_COOKIE, USER_COOKIE, AdminError, AdminService
from app.domain.admin.errors import FORBIDDEN, MSG, SQL_EDITOR_DENIED, VALIDATION
from app.domain.admin.rbac import evaluate
from app.domain.ops.catalog import KIND_ACTION, KINDS, OpsCatalog
from app.domain.ops.pipeline import READ_ACTION, WRITE_ACTION, ConfigPipeline
from app.domain.ops.wizard import WizardService

router = APIRouter(prefix="/admin/v1", tags=["ops"])


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    payload: dict[str, Any]


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_version: int
    reason: str


class WizardBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    target: str
    reason: str = ""


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


def _tokens(request: Request) -> tuple[str | None, str | None]:
    return request.cookies.get(ADMIN_COOKIE), request.cookies.get(USER_COOKIE)


def _admin(request: Request) -> AdminService:
    svc = getattr(request.app.state, "admin_service", None)
    if not isinstance(svc, AdminService):
        svc = AdminService()
        request.app.state.admin_service = svc
    return svc


def _catalog(request: Request) -> OpsCatalog:
    cat = getattr(request.app.state, "ops_catalog", None)
    if not isinstance(cat, OpsCatalog):
        cat = OpsCatalog()
        request.app.state.ops_catalog = cat
    return cat


def _pipe(request: Request) -> ConfigPipeline:
    pipe = getattr(request.app.state, "config_pipeline", None)
    if not isinstance(pipe, ConfigPipeline):
        pipe = ConfigPipeline()
        request.app.state.config_pipeline = pipe
    return pipe


def _wizards(request: Request) -> WizardService:
    wiz = getattr(request.app.state, "wizard_service", None)
    if not isinstance(wiz, WizardService):
        wiz = WizardService()
        request.app.state.wizard_service = wiz
    return wiz


def _require(
    request: Request, action: str
) -> tuple[Any, AdminService, str | None, str | None]:
    admin, user = _tokens(request)
    svc = _admin(request)
    acc = svc.resolve(admin_token=admin, user_cookie=user)
    if not evaluate(acc.role, acc.readonly, action):
        raise AdminError(FORBIDDEN, MSG[FORBIDDEN], http_status=403)
    return acc, svc, admin, user


@router.get("/ops")
async def list_kinds(request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        acc, _, _, _ = _require(request, "alert.read")
    except AdminError as exc:
        return _fail(exc, rid)
    visible = [
        kind for kind in KINDS if evaluate(acc.role, acc.readonly, KIND_ACTION[kind])
    ]
    return JSONResponse(
        status_code=200,
        content=_envelope("0", "ok", rid, {"kinds": visible}),
    )


@router.get("/ops/{kind}")
async def list_ops(kind: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    cursor = str(request.query_params.get("cursor") or "")
    q = str(request.query_params.get("q") or "")
    try:
        limit = int(request.query_params.get("limit") or 50)
        action = _catalog(request).action_for(kind)
        _require(request, action)
        page = _catalog(request).list_page(kind, cursor=cursor, limit=limit, q=q)
    except AdminError as exc:
        return _fail(exc, rid)
    except ValueError:
        return _fail(AdminError(VALIDATION, MSG[VALIDATION], http_status=400), rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, page.as_dict())
    )


@router.get("/ops/{kind}/{item_id}")
async def get_ops(kind: str, item_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        action = _catalog(request).action_for(kind)
        _require(request, action)
        detail = _catalog(request).get(kind, item_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, detail))


@router.get("/ops/{kind}/{item_id}/export")
async def export_ops(kind: str, item_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        action = _catalog(request).action_for(kind)
        _require(request, action)
        payload = _catalog(request).export(kind, item_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, payload))


@router.post("/config")
async def create_draft(body: DraftBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        action = WRITE_ACTION.get(body.kind)
        if action is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        _require(request, action)
        draft = _pipe(request).create_draft(body.kind, body.payload)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, draft.as_dict())
    )


@router.get("/config/{draft_id}")
async def get_draft(draft_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        draft = _pipe(request).get(draft_id)
        _require(request, READ_ACTION[draft.kind])
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, draft.as_dict())
    )


@router.get("/config/{draft_id}/diff")
async def diff_draft(draft_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        draft = _pipe(request).get(draft_id)
        _require(request, READ_ACTION[draft.kind])
        payload = _pipe(request).diff(draft_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, payload))


@router.post("/config/{draft_id}/simulate")
async def simulate_draft(draft_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        draft = _pipe(request).get(draft_id)
        _require(request, WRITE_ACTION[draft.kind])
        payload = _pipe(request).simulate(draft_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, payload))


@router.post("/config/{draft_id}/approve")
async def approve_draft(draft_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        draft = _pipe(request).get(draft_id)
        _require(request, WRITE_ACTION[draft.kind])
        out = _pipe(request).approve(draft_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, out.as_dict())
    )


@router.post("/config/{draft_id}/publish")
async def publish_draft(
    draft_id: str, body: ReasonBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    try:
        draft = _pipe(request).get(draft_id)
        admin, user = _tokens(request)
        svc = _admin(request)
        svc.ensure_action(
            admin_token=admin,
            user_cookie=user,
            action=WRITE_ACTION[draft.kind],
            reason=body.reason,
            audit_denial=True,
            request_id=rid,
            target=draft_id,
        )
        published = _pipe(request).publish(draft_id)
        svc.execute(
            admin_token=admin,
            user_cookie=user,
            action=WRITE_ACTION[draft.kind],
            target=draft_id,
            reason=body.reason,
            request_id=rid,
            before={"version": draft.base_version},
            after={"version": published["version"]},
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, published))


@router.post("/config/{kind}/rollback")
async def rollback_config(
    kind: str, body: RollbackBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    try:
        action = WRITE_ACTION.get(kind)
        if action is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        admin, user = _tokens(request)
        svc = _admin(request)
        svc.ensure_action(
            admin_token=admin,
            user_cookie=user,
            action=action,
            reason=body.reason,
            audit_denial=True,
            request_id=rid,
            target=kind,
        )
        restored = _pipe(request).rollback(kind, body.to_version)
        svc.execute(
            admin_token=admin,
            user_cookie=user,
            action=action,
            target=kind,
            reason=body.reason,
            request_id=rid,
            after={"version": restored["version"]},
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=_envelope("0", "ok", rid, restored))


@router.patch("/config/active")
async def patch_active(request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        _require(request, "price.publish")
        _pipe(request).patch_active("price", {})
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=409,
        content=_envelope("PATCH_ACTIVE_DENIED", "", rid),
    )


@router.post("/wizards")
async def start_wizard(body: WizardBody, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        action = _wizards(request).action_for(body.kind)
        _require(request, action)
        item = _wizards(request).start(
            kind=body.kind, target=body.target, reason=body.reason
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, item.as_dict())
    )


@router.get("/wizards/{wizard_id}")
async def get_wizard(wizard_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        item = _wizards(request).get(wizard_id)
        _require(request, _wizards(request).action_for(item.kind))
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, item.as_dict())
    )


@router.post("/wizards/{wizard_id}/confirm")
async def confirm_wizard(
    wizard_id: str, body: ReasonBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    try:
        item = _wizards(request).get(wizard_id)
        action = _wizards(request).action_for(item.kind)
        _, svc, token, user = _require(request, action)
        out = _wizards(request).confirm(
            wizard_id,
            admin=svc,
            admin_token=token,
            user_cookie=user,
            request_id=rid,
            reason=body.reason,
        )
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, out.as_dict())
    )


@router.post("/wizards/{wizard_id}/cancel")
async def cancel_wizard(wizard_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        item = _wizards(request).get(wizard_id)
        _require(request, _wizards(request).action_for(item.kind))
        out = _wizards(request).cancel(wizard_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, out.as_dict())
    )


@router.post("/sql")
async def deny_sql(request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        admin, user = _tokens(request)
        _admin(request).resolve(admin_token=admin, user_cookie=user)
        raise AdminError(SQL_EDITOR_DENIED, MSG[SQL_EDITOR_DENIED], http_status=403)
    except AdminError as exc:
        return _fail(exc, rid)


@router.patch("/ledger/{entry_id}/balance")
async def deny_balance(entry_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        _require(request, "ledger.edit_balance")
    except AdminError as exc:
        return _fail(exc, rid)
    _ = entry_id
    return JSONResponse(
        status_code=403,
        content=_envelope(FORBIDDEN, MSG[FORBIDDEN], rid),
    )


@router.delete("/audit/{event_id}")
async def deny_delete_audit(event_id: str, request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        admin, user = _tokens(request)
        _admin(request).resolve(admin_token=admin, user_cookie=user)
        _admin(request).audit.delete(event_id)
    except AdminError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=409,
        content=_envelope("IMMUTABLE_AUDIT", MSG["IMMUTABLE_AUDIT"], rid),
    )
