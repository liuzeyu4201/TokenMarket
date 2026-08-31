"""Buyer Project budget, guide, and usage (SF13)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.budget import BudgetError, BudgetService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/projects", tags=["budget"])


class PutBudgetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard_minor: int = Field(ge=0)
    soft_minor: int = Field(ge=0)
    key_id: str | None = None


class AdmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(ge=1)
    key_id: str | None = None
    protocol: str | None = None


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _svc(request: Request) -> BudgetService:
    svc = getattr(request.app.state, "budget_service", None)
    if not isinstance(svc, BudgetService):
        svc = BudgetService()
        request.app.state.budget_service = svc
    return svc


def _fail(exc: BudgetError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(exc.code, exc.message, request_id=rid),
    )


async def _actor(request: Request) -> Any:
    return await resolve_actor(request)


@router.get("/{project_id}/budget")
async def get_budget(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await _actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _svc(request).overview(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BudgetError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.put("/{project_id}/budget")
async def put_budget(
    project_id: uuid.UUID, body: PutBudgetBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await _actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    try:
        pol = _svc(request).put_policy(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            hard_minor=body.hard_minor,
            soft_minor=body.soft_minor,
            key_id=body.key_id,
        )
    except BudgetError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {
                "hard_minor": pol.hard_minor,
                "soft_minor": pol.soft_minor,
                "key_id": pol.key_id,
            },
            request_id=rid,
        ),
    )


@router.post("/{project_id}/budget/admit")
async def admit_budget(
    project_id: uuid.UUID, body: AdmitBody, request: Request
) -> JSONResponse:
    rid = _rid(request)
    actor = await _actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _svc(request).admit(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            amount_minor=body.amount_minor,
            key_id=body.key_id,
        )
    except BudgetError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("/{project_id}/guide")
async def get_guide(project_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await _actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = _svc(request).guide(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
        )
    except BudgetError as exc:
        return _fail(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("/{project_id}/usage")
async def get_usage(
    project_id: uuid.UUID,
    request: Request,
    key_id: str | None = None,
    status: str | None = None,
) -> JSONResponse:
    rid = _rid(request)
    actor = await _actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        rows = _svc(request).usage(
            project_id=project_id,
            owner_id=actor.user_id,
            role=actor.role,
            workspace=actor.workspace,
            key_id=key_id,
            status=status,
        )
    except BudgetError as exc:
        return _fail(exc, rid)
    items = [
        {
            "request_id": r.request_id,
            "key_id": r.key_id,
            "status": r.status,
            "amount_minor": r.amount_minor,
            "reason": r.reason,
        }
        for r in rows
    ]
    return JSONResponse(
        status_code=200, content=success_envelope({"items": items}, request_id=rid)
    )
