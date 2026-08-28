"""Seller API Key onboarding and lifecycle HTTP (SF08/SF09)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.actors import resolve_actor
from app.api.v1.mutation_guard import guard_cookie_mutation
from app.domain.sellerkeys.codes import OnboardingError
from app.domain.sellerkeys.lifecycle import LifecycleService
from app.domain.sellerkeys.service import OnboardingService
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/api/v1/seller-keys", tags=["seller-keys"])

_validation_sema: asyncio.Semaphore | None = None
_validation_sema_n = 0
_T = TypeVar("_T")


def _validation_limit() -> asyncio.Semaphore:
    global _validation_sema, _validation_sema_n
    n = max(1, int(os.environ.get("SELLER_VALIDATION_CONCURRENCY", "8")))
    if _validation_sema is None or _validation_sema_n != n:
        _validation_sema = asyncio.Semaphore(n)
        _validation_sema_n = n
    return _validation_sema


async def _run_validated(fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    """Run blocking provider validation off the event loop, with a global bound."""
    async with _validation_limit():
        return await asyncio.to_thread(fn, *args, **kwargs)


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
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content=error_envelope(
                "INVALID_REQUEST", "缺少 Idempotency-Key", request_id=rid
            ),
        )
    try:
        svc = _onboarding(request)
        out = await _run_validated(
            svc.onboard,
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
    denied = guard_cookie_mutation(request, session_id=actor.session_id)
    if denied is not None:
        return denied
    lc = _lifecycle(request)
    try:
        if op == "pause":
            item = lc.pause(key_id, actor.user_id, actor.role)
        elif op == "resume":
            # Resume re-validates the upstream credential (blocking HTTP).
            item = await _run_validated(
                lc.resume, key_id, actor.user_id, actor.role, rid
            )
        else:
            item = lc.revoke(key_id, actor.user_id, actor.role)
    except OnboardingError as exc:
        return _err(exc, rid)
    return JSONResponse(status_code=200, content=success_envelope(item, request_id=rid))
