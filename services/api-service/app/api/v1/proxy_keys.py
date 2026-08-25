"""Buyer proxy key issue/list/revoke HTTP (SF10)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.actors import resolve_actor
from app.domain.proxykeys.service import ProxyKeyError, ProxyKeyService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/proxy-keys", tags=["proxy-keys"])

_BASE = "/v1/proxy/volcano/chat/completions"


class IssueBody(BaseModel):
    platform: str = "volcano"
    name: str | None = Field(default=None, max_length=64)


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> ProxyKeyService:
    return request.app.state.proxy_key_service  # type: ignore[no-any-return]


@router.post("")
async def issue_proxy_key(
    body: IssueBody,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        issued = _svc(request).issue(
            buyer_id=actor.user_id,
            platform=body.platform,
            name=body.name,
            role=actor.role,
            idempotency_key=idempotency_key,
        )
    except ProxyKeyError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_envelope(exc.code, exc.message, request_id=rid),
        )
    data = {
        "key_id": str(issued.key_id),
        "platform": issued.platform,
        "status": issued.status,
        "masked_suffix": issued.masked_suffix,
        "base_url": _BASE,
        "save_secret": "完整代理 Key 仅展示一次，请立即保存",
        "replayed": issued.replayed,
        "secret": issued.secret_once,
    }
    if issued.secret_once is None:
        data.pop("secret", None)
        data["save_secret"] = "秘密已交付，重放不再回显；可撤销后重新签发"
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("")
async def list_proxy_keys(request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _svc(request).list_mine(actor.user_id, actor.role)
    except ProxyKeyError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_envelope(exc.code, exc.message, request_id=rid),
        )
    payload = [
        {
            "key_id": str(i.key_id),
            "platform": i.platform,
            "status": i.status,
            "masked_suffix": i.masked_suffix,
            "name": i.name,
        }
        for i in items
    ]
    return JSONResponse(
        status_code=200, content=success_envelope(payload, request_id=rid)
    )


@router.post("/{key_id}/revoke")
async def revoke_proxy_key(key_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).revoke(key_id, actor.user_id, actor.role)
    except ProxyKeyError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_envelope(exc.code, exc.message, request_id=rid),
        )
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"key_id": str(rec.key_id), "status": rec.status}, request_id=rid
        ),
    )
