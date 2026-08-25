"""Seller API Key onboarding and lifecycle HTTP (SF08/SF09)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.actors import resolve_actor
from app.domain.sellerkeys.codes import OnboardingError
from app.domain.sellerkeys.lifecycle import LifecycleService
from app.domain.sellerkeys.service import OnboardingService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/seller-keys", tags=["seller-keys"])


class OnboardBody(BaseModel):
    platform: str
    api_key: str = Field(min_length=8, max_length=4096)


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _err(exc: OnboardingError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(exc.code, exc.message, request_id=request_id),
    )


def _onboarding(request: Request) -> OnboardingService:
    return OnboardingService(
        validator=request.app.state.seller_validator,
        encryptor=request.app.state.seller_encryptor,
        store=request.app.state.seller_key_store,
        fingerprint_secret=request.app.state.seller_fp_secret,
    )


def _lifecycle(request: Request) -> LifecycleService:
    return LifecycleService(
        store=request.app.state.seller_key_store,
        encryptor=request.app.state.seller_encryptor,
        validator=request.app.state.seller_validator,
    )


@router.post("")
async def onboard_seller_key(
    body: OnboardBody,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content=error_envelope(
                "INVALID_REQUEST", "缺少 Idempotency-Key", request_id=rid
            ),
        )
    try:
        out = _onboarding(request).onboard(
            seller_id=actor.user_id,
            role=actor.role,
            platform=body.platform,
            api_key=body.api_key,
            idempotency_key=idempotency_key,
            request_id=rid,
        )
    except OnboardingError as exc:
        return _err(exc, rid)
    data: dict[str, Any] = {
        "key_id": str(out.key_id),
        "platform": out.platform,
        "masked_hint": out.masked_hint,
        "remaining_quota": out.remaining_quota,
        "quota_unit": out.quota_unit,
        "administrative_state": out.administrative_state,
        "health_state": out.health_state,
        "last_validated_at": out.last_validated_at.isoformat(),
        "replayed": out.replayed,
    }
    return JSONResponse(status_code=200, content=success_envelope(data, request_id=rid))


@router.get("")
async def list_seller_keys(request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        items = _lifecycle(request).list(actor.user_id, actor.role)
    except OnboardingError as exc:
        return _err(exc, rid)
    return JSONResponse(
        status_code=200, content=success_envelope(items, request_id=rid)
    )


@router.get("/{key_id}")
async def get_seller_key(key_id: uuid.UUID, request: Request) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        item = _lifecycle(request).get(key_id, actor.user_id, actor.role)
    except OnboardingError as exc:
        return _err(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(item, request_id=rid))


@router.post("/{key_id}/pause")
async def pause_seller_key(key_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(key_id, request, "pause")


@router.post("/{key_id}/resume")
async def resume_seller_key(key_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(key_id, request, "resume")


@router.post("/{key_id}/revoke")
async def revoke_seller_key(key_id: uuid.UUID, request: Request) -> JSONResponse:
    return await _transition(key_id, request, "revoke")


async def _transition(key_id: uuid.UUID, request: Request, op: str) -> JSONResponse:
    rid = _rid(request)
    actor = await resolve_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    lc = _lifecycle(request)
    try:
        if op == "pause":
            item = lc.pause(key_id, actor.user_id, actor.role)
        elif op == "resume":
            item = lc.resume(key_id, actor.user_id, actor.role, rid)
        else:
            item = lc.revoke(key_id, actor.user_id, actor.role)
    except OnboardingError as exc:
        return _err(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(item, request_id=rid))
