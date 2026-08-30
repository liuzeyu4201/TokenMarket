"""Project-scoped proxy keys (SF12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.proxykeys.service import IssuedProxyKey, ProxyKeyError, ProxyKeyService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/projects", tags=["project-proxy-keys"])


class IssueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=64)
    protocols: list[str] = Field(min_length=1)
    allowed_models: list[str] | None = None
    allowed_cidrs: list[str] | None = None
    quota_period: str | None = None
    quota_limit: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    idempotency_key: str | None = None


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> ProxyKeyService:
    return request.app.state.proxy_key_service  # type: ignore[no-any-return]


def _public(rec: IssuedProxyKey, *, include_secret: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "key_id": str(rec.key_id),
        "project_id": str(rec.project_id) if rec.project_id else None,
        "name": rec.name,
        "status": rec.status,
        "masked_prefix": rec.masked_prefix,
        "masked_suffix": rec.masked_suffix,
        "protocols": rec.protocols,
        "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
    }
    if include_secret and rec.secret_once:
        data["secret"] = rec.secret_once
        data["save_secret"] = "完整代理 Key 仅展示一次，请立即保存"
    return data


def _fail(exc: ProxyKeyError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(exc.code, exc.message, request_id=rid),
    )


async def _guard(request: Request) -> JSONResponse | tuple[Any, str]:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    return actor, rid


@router.get("/{project_id}/proxy-keys")
async def list_keys(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _svc(request).list_project(actor.user_id, project_id, actor.role)
    except ProxyKeyError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"items": [_public(i, include_secret=False) for i in items]},
            request_id=rid,
        ),
    )


@router.post("/{project_id}/proxy-keys")
async def issue_key(
    project_id: uuid.UUID, body: IssueBody, request: Request
) -> JSONResponse:
    guarded = await _guard(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).issue_for_project(
            buyer_id=actor.user_id,
            project_id=project_id,
            protocols=body.protocols,
            role=actor.role,
            workspace=actor.workspace,
            name=body.name,
            allowed_models=body.allowed_models,
            allowed_cidrs=body.allowed_cidrs,
            quota_period=body.quota_period,
            quota_limit=body.quota_limit,
            expires_at=body.expires_at,
            idempotency_key=body.idempotency_key,
        )
    except ProxyKeyError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=201,
        content=success_envelope(_public(rec, include_secret=True), request_id=rid),
    )


async def _act(
    project_id: uuid.UUID, key_id: uuid.UUID, request: Request, action: str
) -> JSONResponse:
    guarded = await _guard(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    svc = _svc(request)
    try:
        if action == "rotate":
            rec = svc.rotate(key_id, actor.user_id, project_id, actor.role)
            return JSONResponse(
                status_code=200,
                content=success_envelope(
                    _public(rec, include_secret=True), request_id=rid
                ),
            )
        if action == "disable":
            rec = svc.disable(key_id, actor.user_id, project_id, actor.role)
        elif action == "enable":
            rec = svc.enable(key_id, actor.user_id, project_id, actor.role)
        else:
            rec = svc.revoke_project_key(key_id, actor.user_id, project_id, actor.role)
    except ProxyKeyError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(_public(rec, include_secret=False), request_id=rid),
    )


@router.post("/{project_id}/proxy-keys/{key_id}/rotate")
async def rotate_key(
    project_id: uuid.UUID, key_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _act(project_id, key_id, request, "rotate")


@router.post("/{project_id}/proxy-keys/{key_id}/disable")
async def disable_key(
    project_id: uuid.UUID, key_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _act(project_id, key_id, request, "disable")


@router.post("/{project_id}/proxy-keys/{key_id}/enable")
async def enable_key(
    project_id: uuid.UUID, key_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _act(project_id, key_id, request, "enable")


@router.post("/{project_id}/proxy-keys/{key_id}/revoke")
async def revoke_key(
    project_id: uuid.UUID, key_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _act(project_id, key_id, request, "revoke")
