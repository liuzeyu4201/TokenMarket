"""Buyer Project HTTP (SF10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.projects.codes import MODE_IMMUTABLE, MSG, VALIDATION
from app.domain.projects.models import ProjectRecord
from app.domain.projects.service import ProjectError, ProjectService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=128)
    mode: str
    enabled_protocols: list[str] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)
    preview_opt_in: bool = False


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> ProjectService:
    svc = getattr(request.app.state, "project_service", None)
    if not isinstance(svc, ProjectService):
        svc = ProjectService()
        request.app.state.project_service = svc
    return svc


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _payload(rec: ProjectRecord) -> dict[str, Any]:
    return {
        "project_id": str(rec.project_id),
        "owner_account_id": str(rec.owner_account_id),
        "display_name": rec.display_name,
        "mode": rec.mode,
        "status": rec.status,
        "enabled_protocols": rec.enabled_protocol_names(),
        "protocols": [
            {
                "protocol": p.protocol,
                "enabled": p.enabled,
                "enabled_at": _iso(p.enabled_at),
                "disabled_at": _iso(p.disabled_at),
            }
            for p in rec.protocols
        ],
        "created_at": _iso(rec.created_at),
        "updated_at": _iso(rec.updated_at),
        "archived_at": _iso(rec.archived_at),
        "preview_opt_in": bool(rec.preview_opt_in),
    }


def _fail(exc: ProjectError, rid: str) -> JSONResponse:
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


@router.post("")
async def create_project(body: CreateBody, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).create(
            owner_id=actor.user_id,
            display_name=body.display_name,
            mode=body.mode,
            enabled_protocols=body.enabled_protocols,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            idempotency_key=body.idempotency_key,
            preview_opt_in=body.preview_opt_in,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=201, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.get("")
async def list_projects(request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _svc(request).list_mine(
            owner_id=actor.user_id, role=actor.role, workspace=actor.workspace
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"items": [_payload(i) for i in items]}, request_id=rid
        ),
    )


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).get(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.patch("/{project_id}")
async def patch_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        raw = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=error_envelope(VALIDATION, MSG[VALIDATION], request_id=rid),
        )
    if not isinstance(raw, dict):
        return JSONResponse(
            status_code=400,
            content=error_envelope(VALIDATION, MSG[VALIDATION], request_id=rid),
        )
    if "mode" in raw:
        return JSONResponse(
            status_code=400,
            content=error_envelope(MODE_IMMUTABLE, MSG[MODE_IMMUTABLE], request_id=rid),
        )
    extra = set(raw) - {"display_name", "preview_opt_in"}
    if extra or ("display_name" not in raw and "preview_opt_in" not in raw):
        return JSONResponse(
            status_code=400,
            content=error_envelope(VALIDATION, MSG[VALIDATION], request_id=rid),
        )
    try:
        rec = None
        if "display_name" in raw:
            rec = _svc(request).rename(
                project_id=project_id,
                owner_id=actor.user_id,
                display_name=str(raw["display_name"]),
                role=actor.role,
                workspace=actor.workspace,
                request_id=rid,
            )
        if "preview_opt_in" in raw:
            rec = _svc(request).set_preview_opt_in(
                project_id=project_id,
                owner_id=actor.user_id,
                preview_opt_in=bool(raw["preview_opt_in"]),
                role=actor.role,
                workspace=actor.workspace,
                request_id=rid,
            )
        if rec is None:
            return JSONResponse(
                status_code=400,
                content=error_envelope(VALIDATION, MSG[VALIDATION], request_id=rid),
            )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.delete("/{project_id}")
async def delete_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        _svc(request).delete(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope({"deleted": True}, request_id=rid),
    )


async def _transition(
    project_id: uuid.UUID, request: Request, action: str
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).transition(
            project_id=project_id,
            owner_id=actor.user_id,
            action=action,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.post("/{project_id}/activate")
async def activate_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(project_id, request, "activate")


@router.post("/{project_id}/suspend")
async def suspend_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(project_id, request, "suspend")


@router.post("/{project_id}/archive")
async def archive_project(project_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(project_id, request, "archive")


@router.get("/{project_id}/admission")
async def get_admission(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _svc(request).admission(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.post("/{project_id}/protocols/{protocol}/enable")
async def enable_protocol(
    project_id: uuid.UUID, protocol: str, request: Request
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).enable_protocol(
            project_id=project_id,
            owner_id=actor.user_id,
            protocol=protocol,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.post("/{project_id}/protocols/{protocol}/disable")
async def disable_protocol(
    project_id: uuid.UUID, protocol: str, request: Request
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).disable_protocol(
            project_id=project_id,
            owner_id=actor.user_id,
            protocol=protocol,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
        )
    except ProjectError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )
