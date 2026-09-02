"""Internal gateway-facing APIs: routable keys, proxy hash lookup, usage ingest."""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.usage.service import UsageConflictError, UsageRecord, UsageRecorder
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
        nonce, ct, tag, key_ver, rotated = enc.reencrypt(
            nonce, ct, tag, row.get("key_version")
        )
        secret = enc.decrypt(nonce, ct, tag, key_ver).decode("utf-8")
    except ValueError:
        return None
    if rotated:
        row["nonce"] = nonce
        row["ciphertext"] = ct
        row["tag"] = tag
        row["key_version"] = key_ver
    return secret


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
        before_ver = row.get("key_version")
        secret = _decrypt_row(enc, row)
        if secret is None:
            continue
        if row.get("key_version") != before_ver and hasattr(store, "save"):
            store.save(row)
        keys.append(
            {
                "id": str(row["id"]),
                "seller_id": str(row["seller_id"]),
                "api_key": secret,
                "administrative_state": str(row.get("administrative_state")),
                "health_state": str(row.get("health_state")),
                "platform": str(row.get("platform") or "volcano"),
                "remaining_quota": str(row.get("remaining_quota") or ""),
                "official_concurrency": str(row.get("official_concurrency") or ""),
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
    rec = svc.lookup_runtime(secret_hash)
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
        "project_id": str(rec.project_id) if rec.project_id else None,
        "project_mode": None,
        "preview_opt_in": False,
    }
    proj_svc = getattr(request.app.state, "project_service", None)
    if rec.project_id is not None and proj_svc is not None:
        store = getattr(proj_svc, "_store", None)
        getter = getattr(store, "get", None)
        if callable(getter):
            proj = getter(rec.project_id)
            if proj is not None:
                data["project_mode"] = getattr(proj, "mode", None)
                data["preview_opt_in"] = bool(getattr(proj, "preview_opt_in", False))
    return JSONResponse(
        status_code=200, content=success_envelope(data, request_id=_rid(request))
    )


@router.get("/projects/{project_id}/route-snapshot")
async def project_route_snapshot(
    project_id: uuid.UUID,
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _internal_ok(request, x_internal_token)
    if denied is not None:
        return denied
    rid = _rid(request)
    proj_svc = getattr(request.app.state, "project_service", None)
    store = getattr(proj_svc, "_store", None) if proj_svc is not None else None
    getter = getattr(store, "get", None)
    proj = getter(project_id) if callable(getter) else None
    if proj is None:
        return JSONResponse(
            status_code=404,
            content=error_envelope("NOT_FOUND", "资源不存在", request_id=rid),
        )
    bind_svc = getattr(request.app.state, "binding_service", None)
    bind_store = getattr(bind_svc, "_store", None) if bind_svc is not None else None
    lister = getattr(bind_store, "list_by_project", None)
    bindings = lister(project_id) if callable(lister) else []
    conn_svc = getattr(request.app.state, "connection_service", None)
    connections: list[dict[str, Any]] = []
    for rec in bindings:
        cid = getattr(rec, "connection_id", None)
        if cid is None:
            continue
        secret = ""
        base_url = ""
        health = "unknown"
        seller = ""
        provider = ""
        if conn_svc is not None:
            try:
                secret = conn_svc.unwrap(
                    connection_id=cid, purpose="proxy", request_id=rid
                )
            except Exception:
                secret = ""
            cstore = getattr(conn_svc, "_store", None)
            cget = getattr(cstore, "get", None)
            row = cget(cid) if callable(cget) else None
            if row is not None:
                base_url = str(getattr(row, "base_url", "") or "")
                health = str(getattr(row, "health_state", "") or "unknown")
                seller = str(getattr(row, "seller_account_id", "") or "")
                provider = str(getattr(row, "provider", "") or "")
        protocol = str(getattr(rec, "protocol", "") or provider)
        connections.append(
            {
                "connection_id": str(cid),
                "provider": provider or protocol,
                "protocol": protocol,
                "supply_mode": str(getattr(rec, "supply_mode", "") or ""),
                "base_url": base_url,
                "credential": secret,
                "seller_owner_id": seller,
                "health": health or "unknown",
                "lifecycle": str(getattr(rec, "status", "") or "listed"),
            }
        )
    body = {
        "project_id": str(proj.project_id),
        "mode": proj.mode,
        "preview_opt_in": bool(getattr(proj, "preview_opt_in", False)),
        "buyer_owner_id": str(proj.owner_account_id),
        "connections": connections,
    }
    return JSONResponse(status_code=200, content=success_envelope(body, request_id=rid))


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
    if body.partial and body.status_code < 400:
        status = "incomplete"
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
    try:
        stored = recorder.record(rec)
    except UsageConflictError:
        return JSONResponse(
            status_code=409,
            content=error_envelope(
                "USAGE_CONFLICT",
                "用量观察冲突，已保留既有记录",
                request_id=_rid(request),
            ),
        )
    return JSONResponse(
        status_code=200,
        content=success_envelope(
            {"request_id": stored.request_id, "status": stored.status},
            request_id=_rid(request),
        ),
    )
