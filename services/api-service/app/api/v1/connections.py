"""Provider Connection HTTP (SF14). Public paths never decrypt."""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.connections.health import HealthService
from app.domain.connections.models import ConnectionRecord
from app.domain.connections.service import ConnectionError, ConnectionService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/provider-connections", tags=["provider-connections"])
internal_router = APIRouter(
    prefix="/internal/v1/provider-connections", tags=["internal-connections"]
)


class CredentialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str
    project_number: str | None = None
    location: str | None = None


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    supply_mode: str
    region: str | None = None
    purpose: str | None = None
    base_url: str | None = None
    credential: CredentialBody
    idempotency_key: str | None = None


class ReplaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: CredentialBody
    expected_version: int = Field(ge=1)


class UnwrapBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> ConnectionService:
    svc = getattr(request.app.state, "connection_service", None)
    if not isinstance(svc, ConnectionService):
        raise ConnectionError("SERVICE_UNAVAILABLE", "连接服务未就绪", http_status=503)
    return svc


def _health(request: Request) -> HealthService:
    svc = getattr(request.app.state, "health_service", None)
    if not isinstance(svc, HealthService):
        raise ConnectionError("SERVICE_UNAVAILABLE", "健康服务未就绪", http_status=503)
    return svc


def _fail(exc: ConnectionError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(exc.code, exc.message, request_id=rid, data=exc.data),
    )


def _payload(rec: ConnectionRecord) -> dict[str, Any]:
    return rec.to_public()


def _internal_ok(request: Request, token: str | None) -> JSONResponse | None:
    expected = str(
        getattr(request.app.state, "internal_token", "")
        or os.environ.get("INTERNAL_GATEWAY_TOKEN", "")
    )
    if not expected or not token or token != expected:
        return JSONResponse(
            status_code=401,
            content=error_envelope(
                "UNAUTHORIZED", "内部调用未授权", request_id=_rid(request)
            ),
        )
    return None


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
async def create_connection(body: CreateBody, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).create(
            seller_id=actor.user_id,
            provider=body.provider,
            supply_mode=body.supply_mode,
            secret=body.credential.secret,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            region=body.region,
            purpose=body.purpose,
            base_url=body.base_url,
            project_number=body.credential.project_number,
            location=body.credential.location,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    try:
        _health(request).verify(
            connection_id=rec.connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            immediate=True,
        )
        rec = _svc(request).get(
            connection_id=rec.connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ConnectionError:
        pass
    return JSONResponse(
        status_code=201, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.get("")
async def list_connections(request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _svc(request).list_mine(
            seller_id=actor.user_id, role=actor.role, workspace=actor.workspace
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"items": [_payload(i) for i in items]}, request_id=rid
        ),
    )


@router.get("/{connection_id}")
async def get_connection(connection_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rec = _svc(request).get(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.put("/{connection_id}/credential")
async def replace_credential(
    connection_id: uuid.UUID, body: ReplaceBody, request: Request
) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).replace_credential(
            connection_id=connection_id,
            seller_id=actor.user_id,
            secret=body.credential.secret,
            expected_version=body.expected_version,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            project_number=body.credential.project_number,
            location=body.credential.location,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    try:
        _health(request).verify(
            connection_id=rec.connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            immediate=True,
        )
        rec = _svc(request).get(
            connection_id=rec.connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ConnectionError:
        pass
    return JSONResponse(
        status_code=200, content=success_envelope(_payload(rec), request_id=rid)
    )


@router.post("/{connection_id}/verify")
async def verify_connection(connection_id: uuid.UUID, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        out = _health(request).verify(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
            immediate=True,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    data = _payload(out["connection"])
    data["category"] = out["category"]
    data["capabilities"] = out["capabilities"]
    data["detail"] = out["detail"]
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("/{connection_id}/health")
async def get_health(connection_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _health(request).public_health(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("/{connection_id}/capabilities")
async def list_capabilities(connection_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        snaps = _health(request).list_snapshots(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    items = [
        {
            "version": s.version,
            "capabilities": s.capabilities,
            "created_at": s.created_at.isoformat(),
        }
        for s in snaps
    ]
    return JSONResponse(
        status_code=200, content=success_envelope({"items": items}, request_id=rid)
    )


@router.delete("/{connection_id}")
async def delete_connection(connection_id: uuid.UUID, request: Request) -> JSONResponse:
    guarded = await _guard_write(request)
    if isinstance(guarded, JSONResponse):
        return guarded
    actor, rid = guarded
    try:
        rec = _svc(request).get(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
        fingerprint = rec.credential_fingerprint
        _svc(request).delete(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            request_id=rid,
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "connection_id": str(connection_id),
                "status": "deleted",
                "credential_fingerprint": fingerprint,
            },
            request_id=rid,
        ),
    )


@internal_router.post("/{connection_id}/unwrap")
async def unwrap_connection(
    connection_id: uuid.UUID,
    body: UnwrapBody,
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    rid = _rid(request)
    try:
        secret = _svc(request).unwrap(
            connection_id=connection_id, purpose=body.purpose, request_id=rid
        )
    except ConnectionError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"secret": secret, "purpose": body.purpose}, request_id=rid
        ),
    )


@internal_router.get("/{connection_id}/health")
async def internal_health(
    connection_id: uuid.UUID,
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    rid = _rid(request)
    try:
        fact = _health(request).health_fact(connection_id)
    except ConnectionError as exc:
        return _fail(exc, rid)
    if fact is None:
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
        )
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "connection_id": str(fact.connection_id),
                "health_state": fact.health_state,
                "reason": fact.reason,
                "checked_at": (
                    fact.checked_at.isoformat() if fact.checked_at else None
                ),
                "capability_version": fact.capability_version,
                "routable": fact.routable,
            },
            request_id=rid,
        ),
    )
