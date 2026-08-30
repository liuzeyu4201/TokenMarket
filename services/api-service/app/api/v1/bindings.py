"""Provider Binding HTTP (SF11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.bindings.models import BindingRecord
from app.domain.bindings.service import BindingError, BindingService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/projects", tags=["bindings"])
internal_router = APIRouter(prefix="/internal/v1/bindings", tags=["internal-bindings"])


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str
    supply_mode: str
    allowed_providers: list[str] | None = None
    allowed_models: list[str] | None = None
    allowed_regions: list[str] | None = None
    connection_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=1)


class AdmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str
    provider: str
    model: str | None = None


class DegradeBody(BaseModel):
    connection_id: uuid.UUID


class ReplaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_connection_id: uuid.UUID
    buyer_confirmed: bool
    reason: str
    step_up: bool


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> BindingService:
    svc = getattr(request.app.state, "binding_service", None)
    if not isinstance(svc, BindingService):
        svc = BindingService()
        request.app.state.binding_service = svc
    return svc


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _payload(rec: BindingRecord) -> dict[str, Any]:
    return {
        "binding_id": str(rec.binding_id),
        "project_id": str(rec.project_id),
        "protocol": rec.protocol,
        "supply_mode": rec.supply_mode,
        "status": rec.status,
        "version": rec.version,
        "allowed_providers": rec.allowed_providers,
        "allowed_models": rec.allowed_models,
        "allowed_regions": rec.allowed_regions,
        "connection_id": str(rec.connection_id) if rec.connection_id else None,
        "draining_connection_id": (
            str(rec.draining_connection_id) if rec.draining_connection_id else None
        ),
        "published_at": _iso(rec.published_at),
        "created_at": _iso(rec.created_at),
    }


def _fail(exc: BindingError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(exc.code, exc.message, request_id=rid, data=exc.data),
    )


async def _guard_write(request: Request) -> JSONResponse | tuple[Any, str]:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    return actor, rid


@router.get("/{project_id}/bindings")
async def list_bindings(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _svc(request).list_mine(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"items": [_payload(i) for i in items]}, request_id=rid
        ),
    )


@router.post("/{project_id}/bindings")
async def create_binding(
    project_id: uuid.UUID, body: CreateBody, request: Request
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).create(
            project_id=project_id,
            owner_id=actor.user_id,
            protocol=body.protocol,
            supply_mode=body.supply_mode,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            allowed_providers=body.allowed_providers,
            allowed_models=body.allowed_models,
            allowed_regions=body.allowed_regions,
            connection_id=body.connection_id,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=201, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.get("/{project_id}/bindings/active/{protocol}")
async def get_active(
    project_id: uuid.UUID, protocol: str, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).active(
            project_id=project_id,
            protocol=protocol,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.post("/{project_id}/bindings/admit")
async def admit_binding(
    project_id: uuid.UUID, body: AdmitBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _svc(request).admit(
            project_id=project_id,
            owner_id=actor.user_id,
            protocol=body.protocol,
            provider=body.provider,
            model=body.model,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("/{project_id}/bindings/{binding_id}")
async def get_binding(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).get(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    if rec.project_id != project_id:
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
        )
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.get("/{project_id}/bindings/{binding_id}/sdk-hint")
async def sdk_hint(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        hint = _svc(request).sdk_hint(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(hint, request_id=rid))


async def _mutate(
    project_id: uuid.UUID,
    binding_id: uuid.UUID,
    request: Request,
    action: str,
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    svc = _svc(request)
    try:
        if action == "validate":
            rec = svc.validate(
                binding_id=binding_id,
                owner_id=actor.user_id,
                role=actor.role,
                workspace=actor.workspace,
                request_id=rid,
            )
        elif action == "publish":
            rec = svc.publish(
                binding_id=binding_id,
                owner_id=actor.user_id,
                role=actor.role,
                workspace=actor.workspace,
                request_id=rid,
            )
        else:
            rec = svc.deactivate(
                binding_id=binding_id,
                owner_id=actor.user_id,
                role=actor.role,
                workspace=actor.workspace,
                request_id=rid,
            )
    except BindingError as exc:
        return _fail(exc, rid)
    if rec.project_id != project_id:
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
        )
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.post("/{project_id}/bindings/{binding_id}/validate")
async def validate_binding(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _mutate(project_id, binding_id, request, "validate")


@router.post("/{project_id}/bindings/{binding_id}/publish")
async def publish_binding(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _mutate(project_id, binding_id, request, "publish")


@router.post("/{project_id}/bindings/{binding_id}/deactivate")
async def deactivate_binding(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    return await _mutate(project_id, binding_id, request, "deactivate")


@router.get("/{project_id}/bindings/{binding_id}/replace-preview")
async def preview_replace(
    project_id: uuid.UUID, binding_id: uuid.UUID, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).get(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
        if rec.project_id != project_id:
            return JSONResponse(
                status_code=404,
                content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
            )
        data = _svc(request).replace_preview(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.post("/{project_id}/bindings/{binding_id}/replace")
async def replace_binding(
    project_id: uuid.UUID,
    binding_id: uuid.UUID,
    body: ReplaceBody,
    request: Request,
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).get(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
        if rec.project_id != project_id:
            return JSONResponse(
                status_code=404,
                content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
            )
        rec = _svc(request).replace(
            binding_id=binding_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            new_connection_id=body.new_connection_id,
            buyer_confirmed=body.buyer_confirmed,
            reason=body.reason,
            step_up=body.step_up,
        )
    except BindingError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@internal_router.post("/degrade")
async def degrade_bindings(
    body: DegradeBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    rid = _rid(request)
    expected = str(getattr(request.app.state, "internal_token", "") or "")
    if not expected or token != expected:
        return JSONResponse(
            status_code=401,
            content=error_envelope("UNAUTHORIZED", "内部调用未授权", request_id=rid),
        )
    n = _svc(request).degrade_for_connection(body.connection_id, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope({"degraded": n}, request_id=rid),
    )
