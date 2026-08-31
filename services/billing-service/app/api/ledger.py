"""Internal ledger HTTP (SF28). No recharge or withdraw."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.domain.ledger import LedgerError, LedgerService, account_id_for

router = APIRouter(prefix="/internal/v1/ledger", tags=["ledger"])


class SeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    project_id: str
    key_id: str
    account_grant: int = Field(ge=0)
    project_grant: int = Field(ge=0)
    key_grant: int = Field(ge=0)


class ReserveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    idempotency_key: str
    account_id: str
    project_id: str
    key_id: str
    amount_minor: int = Field(gt=0)
    rate_version: str


class SettleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    buyer_debit: int = Field(ge=0)
    seller_earning: int = Field(ge=0)
    spread: int = Field(ge=0)
    seller_id: str
    rate_version: str
    evidence_digest: str = ""


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    reason: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(
    code: str, message: str, request_id: str, data: Any = None
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id,
        "timestamp": _now(),
    }


def _svc(request: Request) -> LedgerService:
    svc = getattr(request.app.state, "ledger_service", None)
    if not isinstance(svc, LedgerService):
        svc = LedgerService()
        request.app.state.ledger_service = svc
    return svc


def _auth(request: Request, token: str | None) -> JSONResponse | None:
    expected = str(getattr(request.app.state, "internal_token", "") or "")
    if not expected or token != expected:
        rid = str(uuid.uuid4())
        return JSONResponse(
            status_code=401,
            content=_envelope("UNAUTHORIZED", "内部调用未授权", rid),
        )
    return None


def _fail(exc: LedgerError, rid: str) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_envelope(exc.code, exc.message, rid),
    )


@router.post("/seed-test-quota")
async def seed_test_quota(
    body: SeedBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    rid = str(uuid.uuid4())
    try:
        _svc(request).seed_quota(
            account_id=body.account_id,
            project_id=body.project_id,
            key_id=body.key_id,
            account_grant=body.account_grant,
            project_grant=body.project_grant,
            key_grant=body.key_grant,
            request_id=rid,
        )
    except LedgerError as exc:
        return _fail(exc, rid)
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"seeded": True})
    )


@router.post("/reserve")
async def reserve(
    body: ReserveBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        rec = _svc(request).reserve(
            request_id=body.request_id,
            idempotency_key=body.idempotency_key,
            account_id=body.account_id,
            project_id=body.project_id,
            key_id=body.key_id,
            amount_minor=body.amount_minor,
            rate_version=body.rate_version,
        )
    except LedgerError as exc:
        return _fail(exc, body.request_id)
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            body.request_id,
            {
                "reservation_id": rec.reservation_id,
                "status": rec.status,
                "amount_minor": rec.amount_minor,
            },
        ),
    )


@router.post("/settle")
async def settle(
    body: SettleBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        journal = _svc(request).settle(
            request_id=body.request_id,
            buyer_debit=body.buyer_debit,
            seller_earning=body.seller_earning,
            spread=body.spread,
            seller_id=body.seller_id,
            rate_version=body.rate_version,
            evidence_digest=body.evidence_digest,
        )
    except LedgerError as exc:
        return _fail(exc, body.request_id)
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            body.request_id,
            {"journal_id": journal.journal_id, "entry_ids": journal.entry_ids},
        ),
    )


@router.post("/release")
async def release(
    body: RequestBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        rec = _svc(request).release(request_id=body.request_id)
    except LedgerError as exc:
        return _fail(exc, body.request_id)
    return JSONResponse(
        status_code=200,
        content=_envelope("0", "ok", body.request_id, {"status": rec.status}),
    )


@router.post("/unresolved")
async def unresolved(
    body: RequestBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        rec = _svc(request).mark_unresolved(
            request_id=body.request_id, reason=body.reason
        )
    except LedgerError as exc:
        return _fail(exc, body.request_id)
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            body.request_id,
            {"status": rec.status, "reason": rec.unresolved_reason},
        ),
    )


@router.get("/balance/{kind}/{raw_id}")
async def balance(
    kind: str,
    raw_id: str,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    rid = str(uuid.uuid4())
    try:
        acc = account_id_for(kind, raw_id)  # type: ignore[arg-type]
        bal = _svc(request).rebuild(acc)
    except (LedgerError, TypeError, ValueError) as exc:
        if isinstance(exc, LedgerError):
            return _fail(exc, rid)
        return JSONResponse(
            status_code=400, content=_envelope("VALIDATION", "请求参数不合法", rid)
        )
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            rid,
            {
                "account_id": bal.account_id,
                "available": bal.available,
                "reserved": bal.reserved,
                "settled_debit": bal.settled_debit,
                "settled_credit": bal.settled_credit,
            },
        ),
    )
