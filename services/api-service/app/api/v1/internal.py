"""Internal gateway-facing APIs: routable keys, proxy hash lookup, usage ingest."""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.usage.service import UsageRecord, UsageRecorder
from app.schemas.envelope import error_envelope, success_envelope

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class HealthBody(BaseModel):
    health_state: str = Field(min_length=1, max_length=32)


class UsageBody(BaseModel):
    request_id: str
    proxy_key_id: str | None = None
    api_key_id: str | None = None
    buyer_id: str | None = None
    seller_id: str | None = None
    platform: str = "volcano"
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    usage_source: str = "not_available"
    partial: bool = False
    latency_ms: int = 0
    status_code: int = 0
    end_reason: str = ""


def _rid(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


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


def _decrypt_row(enc: CredentialEncryptor, row: dict[str, Any]) -> str | None:
    ct, nonce, tag = row.get("ciphertext"), row.get("nonce"), row.get("tag")
    if not ct or not nonce or not tag:
        return None
    try:
        return enc.decrypt(nonce, ct, tag).decode("utf-8")
    except ValueError:
        return None


@router.get("/seller-keys/routable")
async def list_routable(
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    store = request.app.state.seller_key_store
    enc: CredentialEncryptor = request.app.state.seller_encryptor
    keys: list[dict[str, str]] = []
    for row in store.list_routable():
        secret = _decrypt_row(enc, row)
        if secret is None:
            continue
        keys.append(
            {
                "id": str(row["id"]),
                "seller_id": str(row["seller_id"]),
                "api_key": secret,
                "administrative_state": str(row.get("administrative_state")),
                "health_state": str(row.get("health_state")),
                "platform": str(row.get("platform") or "volcano"),
            }
        )
    return JSONResponse(
        status_code=200, content=success_envelope(keys, request_id=_rid(request))
    )


@router.post("/seller-keys/{key_id}/health")
async def patch_health(
    key_id: uuid.UUID,
    body: HealthBody,
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    store = request.app.state.seller_key_store
    store.apply_health(key_id, body.health_state)
    return JSONResponse(
        status_code=200,
        content=success_envelope({"id": str(key_id)}, request_id=_rid(request)),
    )


@router.get("/proxy-keys/by-hash")
async def lookup_proxy_hash(
    request: Request,
    secret_hash: str = Query(..., alias="hash", min_length=16, max_length=128),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    svc = request.app.state.proxy_key_service
    rec = svc.lookup_hash(secret_hash)
    if rec is None:
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "资源不存在", request_id=_rid(request)),
        )
    data = {
        "key_id": str(rec.key_id),
        "buyer_id": str(rec.buyer_id),
        "platform": rec.platform,
        "status": rec.status,
    }
    return JSONResponse(
        status_code=200, content=success_envelope(data, request_id=_rid(request))
    )


@router.post("/usage-observations")
async def ingest_usage(
    body: UsageBody,
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    recorder: UsageRecorder = request.app.state.usage_recorder
    buyer: uuid.UUID | None = None
    seller: uuid.UUID | None = None
    try:
        if body.buyer_id:
            buyer = uuid.UUID(body.buyer_id)
        if body.seller_id:
            seller = uuid.UUID(body.seller_id)
    except ValueError:
        buyer = None
        seller = None
    status = "complete" if body.usage_source == "official" else "missing"
    if body.status_code >= 400 and not body.partial:
        status = "failed"
    rec = UsageRecord(
        request_id=body.request_id,
        buyer_id=buyer,
        platform=body.platform,
        model=body.model,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
        total_tokens=body.total_tokens,
        status=status,
        source=body.usage_source,
        proxy_key_id=body.proxy_key_id,
        api_key_id=body.api_key_id,
        seller_id=seller,
        partial=body.partial,
        latency_ms=body.latency_ms,
        status_code=body.status_code,
        end_reason=body.end_reason,
    )
    if status == "failed":
        rec.status = "failed"
    stored = recorder.record(rec)
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"request_id": stored.request_id}, request_id=_rid(request)
        ),
    )
