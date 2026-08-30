"""Seller supply workbench HTTP (SF17)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.connections.models import ConnectionRecord
from app.domain.connections.service import ConnectionError, ConnectionService
from app.domain.workbench.service import (
    ConnectionSnapshot,
    WorkbenchError,
    WorkbenchService,
)
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/seller", tags=["seller-workbench"])


class QuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    multiplier_bps: int = Field(ge=0)


class CapacityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    declared_capacity: int = Field(ge=0)


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _wb(request: Request) -> WorkbenchService:
    svc = getattr(request.app.state, "workbench_service", None)
    if not isinstance(svc, WorkbenchService):
        raise WorkbenchError("SERVICE_UNAVAILABLE", "工作台未就绪", 503)
    return svc


def _conn(request: Request) -> ConnectionService:
    svc = getattr(request.app.state, "connection_service", None)
    if not isinstance(svc, ConnectionService):
        raise ConnectionError("SERVICE_UNAVAILABLE", "连接服务未就绪", http_status=503)
    return svc


def _fail(exc: WorkbenchError | ConnectionError, rid: str) -> JSONResponse:
    status = getattr(exc, "http_status", 400)
    return JSONResponse(
        status_code=status,
        content=error_envelope(exc.code, exc.message, request_id=rid),
    )


async def _guard(request: Request) -> JSONResponse | tuple[Any, str]:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    if actor.workspace != "seller" and actor.role not in {"seller", "both"}:
        return JSONResponse(
            status_code=403,
            content=error_envelope("FORBIDDEN", "请使用卖家工作区", request_id=rid),
        )
    if actor.workspace == "buyer":
        return JSONResponse(
            status_code=403,
            content=error_envelope("FORBIDDEN", "请切换到卖家工作区", request_id=rid),
        )
    return actor, rid


async def _guard_write(request: Request) -> JSONResponse | tuple[Any, str]:
    got = await _guard(request)
    if isinstance(got, JSONResponse):
        return got
    actor, rid = got
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    return actor, rid


def _snap(rec: ConnectionRecord) -> ConnectionSnapshot:
    return ConnectionSnapshot(
        connection_id=str(rec.connection_id),
        seller_account_id=str(rec.seller_account_id),
        provider=rec.provider,
        supply_mode=rec.supply_mode,
        lifecycle_state=rec.lifecycle_state,
        health_state=rec.health_state,
        health_reason=rec.health_reason,
    )


@router.get("/workbench")
async def list_workbench(request: Request) -> JSONResponse:
    rid = _rid(request)
    try:
        got = await _guard(request)
        if isinstance(got, JSONResponse):
            return got
        actor, rid = got
        wb = _wb(request)
        conn = _conn(request)
        rows = conn.list_mine(
            seller_id=actor.user_id, role=actor.role, workspace=actor.workspace
        )
        cards = [wb.card(_snap(r), str(actor.user_id)) for r in rows]
        return JSONResponse(success_envelope({"items": cards}, request_id=rid))
    except (WorkbenchError, ConnectionError) as exc:
        return _fail(exc, rid)


@router.post("/workbench/{connection_id}/quotes")
async def post_quote(
    connection_id: uuid.UUID, body: QuoteBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    try:
        got = await _guard_write(request)
        if isinstance(got, JSONResponse):
            return got
        actor, rid = got
        conn = _conn(request)
        rec = conn.get(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
        rev = _wb(request).submit_quote(
            seller_id=str(actor.user_id),
            connection_id=str(connection_id),
            multiplier_bps=body.multiplier_bps,
            actor_id=str(actor.user_id),
            owner_id=str(rec.seller_account_id),
        )
        return JSONResponse(
            success_envelope(
                {
                    "seq": rev.seq,
                    "multiplier_bps": rev.multiplier_bps,
                    "rate_version": rev.rate_version,
                },
                request_id=rid,
            )
        )
    except (WorkbenchError, ConnectionError) as exc:
        return _fail(exc, rid)


@router.post("/workbench/{connection_id}/capacity")
async def post_capacity(
    connection_id: uuid.UUID, body: CapacityBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    try:
        got = await _guard_write(request)
        if isinstance(got, JSONResponse):
            return got
        actor, rid = got
        conn = _conn(request)
        rec = conn.get(
            connection_id=connection_id,
            seller_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
        cap = _wb(request).set_capacity(
            seller_id=str(actor.user_id),
            connection_id=str(connection_id),
            declared_capacity=body.declared_capacity,
            actor_id=str(actor.user_id),
            owner_id=str(rec.seller_account_id),
        )
        return JSONResponse(
            success_envelope({"declared_capacity": cap}, request_id=rid)
        )
    except (WorkbenchError, ConnectionError) as exc:
        return _fail(exc, rid)
