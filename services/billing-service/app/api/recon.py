"""Internal recon HTTP (SF29)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.domain.ledger import LedgerError, LedgerService
from app.domain.recon import EvidenceEvent, ReconService

router = APIRouter(prefix="/internal/v1/recon", tags=["recon"])


class EventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    request_id: str
    kind: str
    buyer_debit: int | None = None
    seller_earning: int | None = None
    spread: int | None = None
    seller_id: str = "seller-1"
    rate_version: str | None = None
    evidence_digest: str = ""
    connection_id: str = ""
    computed_buyer: int | None = None


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str


class ReverseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    actor: str
    role: str
    step_up: bool
    reason: str
    preview_id: str


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


def _auth(request: Request, token: str | None) -> JSONResponse | None:
    expected = str(getattr(request.app.state, "internal_token", "") or "")
    if not expected or token != expected:
        return JSONResponse(
            status_code=401,
            content=_envelope("UNAUTHORIZED", "内部调用未授权", str(uuid.uuid4())),
        )
    return None


def _ledger(request: Request) -> LedgerService:
    svc = getattr(request.app.state, "ledger_service", None)
    if not isinstance(svc, LedgerService):
        svc = LedgerService()
        request.app.state.ledger_service = svc
    return svc


def _recon(request: Request) -> ReconService:
    svc = getattr(request.app.state, "recon_service", None)
    if not isinstance(svc, ReconService):
        svc = ReconService(_ledger(request))
        request.app.state.recon_service = svc
    return svc


@router.post("/events")
async def ingest_event(
    body: EventBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        out = _recon(request).ingest(
            EvidenceEvent(
                event_id=body.event_id,
                request_id=body.request_id,
                kind=body.kind,  # type: ignore[arg-type]
                buyer_debit=body.buyer_debit,
                seller_earning=body.seller_earning,
                spread=body.spread,
                seller_id=body.seller_id,
                rate_version=body.rate_version,
                evidence_digest=body.evidence_digest,
                connection_id=body.connection_id,
                computed_buyer=body.computed_buyer,
            )
        )
    except LedgerError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, body.request_id),
        )
    data: dict[str, Any] = {"accepted": True}
    if out is not None and hasattr(out, "reason_code"):
        data["reason_code"] = getattr(out, "reason_code")
        data["status"] = getattr(out, "status")
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", body.request_id, data)
    )


@router.post("/tick")
async def tick(
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    n = _recon(request).tick()
    rid = str(uuid.uuid4())
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"processed": n})
    )


@router.get("/unresolved")
async def list_unresolved(
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    rid = str(uuid.uuid4())
    items = [
        {
            "request_id": c.request_id,
            "reason_code": c.reason_code,
            "amount_exposure_minor": c.amount_exposure_minor,
            "status": c.status,
            "owner": c.owner,
        }
        for c in _recon(request).cases()
    ]
    return JSONResponse(
        status_code=200, content=_envelope("0", "ok", rid, {"items": items})
    )


@router.post("/reverse/preview")
async def reverse_preview(
    body: PreviewBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        prev = _recon(request).preview_reverse(body.request_id)
    except LedgerError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, body.request_id),
        )
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            body.request_id,
            {
                "preview_id": prev.preview_id,
                "original_entry_ids": prev.original_entry_ids,
                "net_buyer_delta": prev.net_buyer_delta,
            },
        ),
    )


@router.post("/reverse")
async def reverse_apply(
    body: ReverseBody,
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    try:
        journal = _recon(request).apply_reverse(
            request_id=body.request_id,
            actor=body.actor,
            role=body.role,
            step_up=body.step_up,
            reason=body.reason,
            preview_id=body.preview_id,
        )
    except LedgerError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, body.request_id),
        )
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0", "ok", body.request_id, {"journal_id": journal.journal_id}
        ),
    )


@router.get("/daily")
async def daily(
    request: Request,
    token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> JSONResponse:
    denied = _auth(request, token)
    if denied is not None:
        return denied
    report = _recon(request).daily_report()
    rid = str(uuid.uuid4())
    return JSONResponse(
        status_code=200,
        content=_envelope(
            "0",
            "ok",
            rid,
            {
                "balanced": report.balanced,
                "orphan_request_ids": report.orphan_request_ids,
                "ticket_count": report.ticket_count,
                "open_unresolved": report.open_unresolved,
                "aggregate_matches_detail": report.aggregate_matches_detail,
            },
        ),
    )
