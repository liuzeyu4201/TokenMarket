"""Idempotent evidence ingest, unresolved recovery, variance tickets, reverse."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.domain.ledger.errors import (
    ALREADY_TERMINAL,
    FORBIDDEN_ROLE,
    MSG,
    STEP_UP_REQUIRED,
    VALIDATION,
    LedgerError,
)
from app.domain.ledger.models import Journal
from app.domain.ledger.service import LedgerService
from app.domain.recon.models import (
    DailyReport,
    EvidenceEvent,
    ReconTicket,
    ReversePreview,
    UnresolvedCase,
)

# STEP_UP_REQUIRED may be added to ledger errors; fallback below.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


REASON_FOR_KIND = {
    "parse_failed": "PARSE_FAILED",
    "async_pending": "ASYNC_INCOMPLETE",
    "missing_amount": "MISSING_AMOUNT",
    "missing_usage": "MISSING_USAGE",
}


class ReconService:
    def __init__(
        self,
        ledger: LedgerService,
        *,
        variance_threshold: int = 0,
        sla: timedelta = timedelta(hours=1),
        max_per_tick: int = 50,
        now: Callable[[], datetime] | None = None,
        owner: str = "billing-oncall",
    ) -> None:
        self._ledger = ledger
        self._threshold = variance_threshold
        self._sla = sla
        self._max = max_per_tick
        self._now = now or _now
        self._owner = owner
        self._seen: set[str] = set()
        self._cases: dict[str, UnresolvedCase] = {}
        self._tickets: list[ReconTicket] = []
        self._audits: list[dict[str, object]] = []
        self._previews: dict[str, ReversePreview] = {}
        self._amounts: dict[str, tuple[int, int, int, str]] = {}
        self._rate: dict[str, str] = {}
        self._conn: dict[str, str] = {}

    def ingest(self, event: EvidenceEvent) -> UnresolvedCase | Journal | None:
        if event.event_id in self._seen:
            return None
        self._seen.add(event.event_id)
        rec = self._ledger._require_res(event.request_id)
        rate = rec.rate_version
        self._rate[event.request_id] = rate
        if event.connection_id:
            self._conn[event.request_id] = event.connection_id
        if event.kind in REASON_FOR_KIND:
            return self._open_case(event, rec.amount_minor, rate)
        if event.kind in ("reported_cost", "usage_rated"):
            return self._settle_or_delta(event, rec, rate)
        return None

    def tick(self) -> int:
        now = self._now()
        processed = 0
        for case in list(self._cases.values()):
            if processed >= self._max:
                break
            if case.status != "open":
                continue
            if case.sla_until and now >= case.sla_until:
                case.next_action = "manual"
                case.status = "manual"
                case.updated_at = now
                continue
            if case.retry_at and now < case.retry_at:
                continue
            if case.request_id in self._amounts:
                buyer, seller, spread, sid = self._amounts[case.request_id]
                rate = self._rate.get(case.request_id, "")
                self._ledger.settle(
                    request_id=case.request_id,
                    buyer_debit=buyer,
                    seller_earning=seller,
                    spread=spread,
                    seller_id=sid,
                    rate_version=rate
                    or self._ledger._require_res(case.request_id).rate_version,
                )
                case.status = "recovered"
                case.updated_at = now
                processed += 1
            else:
                case.next_action = "retry"
                case.retry_at = now + timedelta(minutes=5)
                case.updated_at = now
                processed += 1
        return processed

    def cases(self) -> list[UnresolvedCase]:
        return list(self._cases.values())

    def tickets(self) -> list[ReconTicket]:
        return list(self._tickets)

    def audits(self) -> list[dict[str, object]]:
        return list(self._audits)

    def preview_reverse(self, request_id: str) -> ReversePreview:
        rec = self._ledger._require_res(request_id)
        if rec.status != "consumed":
            raise LedgerError(ALREADY_TERMINAL, MSG[ALREADY_TERMINAL])
        originals = [
            e.entry_id
            for e in self._ledger.entries()
            if e.request_id == request_id and e.status == "settled"
        ]
        buyer, _ = self._ledger.net_settled(request_id, "buyer_quota")
        prev = ReversePreview(
            preview_id=_id(),
            request_id=request_id,
            original_entry_ids=originals,
            net_buyer_delta=-buyer,
        )
        self._previews[prev.preview_id] = prev
        return prev

    def apply_reverse(
        self,
        *,
        request_id: str,
        actor: str,
        role: str,
        step_up: bool,
        reason: str,
        preview_id: str,
    ) -> Journal:
        if role not in {"admin", "finance"}:
            raise LedgerError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)
        if not step_up:
            raise LedgerError(STEP_UP_REQUIRED, MSG[STEP_UP_REQUIRED], http_status=409)
        if not str(reason).strip():
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        prev = self._previews.get(preview_id)
        if prev is None or prev.request_id != request_id:
            raise LedgerError(VALIDATION, MSG[VALIDATION], http_status=400)
        original_ids = set(prev.original_entry_ids)
        journal = self._ledger.reverse(request_id=request_id, reason=reason)
        still = {e.entry_id for e in self._ledger.entries()}
        if not original_ids.issubset(still):
            raise LedgerError("IMMUTABLE_ENTRY", "原分录必须保留")
        self._audits.append(
            {
                "actor": actor,
                "role": role,
                "step_up": True,
                "reason": reason.strip(),
                "request_id": request_id,
                "preview_id": preview_id,
                "journal_id": journal.journal_id,
                "at": self._now().isoformat(),
            }
        )
        return journal

    def daily_report(self) -> DailyReport:
        orphans: list[str] = []
        for rec in self._ledger.list_reservations():
            if rec.status in ("consumed", "released"):
                continue
            case = self._cases.get(rec.request_id)
            if rec.status == "unresolved" and case is not None:
                continue
            if rec.status == "held" and case is None:
                orphans.append(rec.request_id)
            elif rec.status == "unresolved" and case is None:
                orphans.append(rec.request_id)
        balanced = True
        for rec in self._ledger.list_reservations():
            if rec.status != "consumed":
                continue
            b, _ = self._ledger.net_settled(rec.request_id, "buyer_quota")
            _, s = self._ledger.net_settled(rec.request_id, "seller_earning")
            _, p = self._ledger.net_settled(rec.request_id, "platform_spread")
            if b != s + p:
                balanced = False
                self._tickets.append(
                    ReconTicket(
                        ticket_id=_id(),
                        kind="UNBALANCED",
                        request_id=rec.request_id,
                        detail=f"buyer={b} seller={s} spread={p}",
                        created_at=self._now(),
                    )
                )
        for oid in orphans:
            self._tickets.append(
                ReconTicket(
                    ticket_id=_id(),
                    kind="ORPHAN",
                    request_id=oid,
                    detail="reservation without terminal state or case",
                    created_at=self._now(),
                )
            )
        open_n = sum(1 for c in self._cases.values() if c.status in ("open", "manual"))
        return DailyReport(
            balanced=balanced,
            orphan_request_ids=orphans,
            ticket_count=len(self._tickets),
            open_unresolved=open_n,
            aggregate_matches_detail=balanced and not orphans,
        )

    def _open_case(
        self, event: EvidenceEvent, exposure: int, rate: str
    ) -> UnresolvedCase:
        rec = self._ledger.mark_unresolved(
            request_id=event.request_id, reason=REASON_FOR_KIND[event.kind]
        )
        now = self._now()
        case = UnresolvedCase(
            request_id=event.request_id,
            reason_code=REASON_FOR_KIND[event.kind],  # type: ignore[arg-type]
            amount_exposure_minor=exposure,
            next_action="wait_callback",
            owner=self._owner,
            status="open",
            missing_evidence=event.kind,
            retry_at=now + timedelta(minutes=1),
            sla_until=now + self._sla,
            connection_id=event.connection_id or self._conn.get(event.request_id, ""),
            rate_version=rate,
            updated_at=now,
        )
        self._cases[event.request_id] = case
        _ = rec
        return case

    def _settle_or_delta(
        self, event: EvidenceEvent, rec: object, rate: str
    ) -> Journal | None:
        buyer = event.buyer_debit
        seller = event.seller_earning
        spread = event.spread
        if buyer is None or seller is None or spread is None:
            return None
        if (
            event.kind == "reported_cost"
            and event.computed_buyer is not None
            and abs(buyer - event.computed_buyer) > self._threshold
        ):
            self._tickets.append(
                ReconTicket(
                    ticket_id=_id(),
                    kind="VARIANCE",
                    request_id=event.request_id,
                    detail="reported vs computed",
                    created_at=self._now(),
                    reported_minor=buyer,
                    computed_minor=event.computed_buyer,
                )
            )
        self._amounts[event.request_id] = (buyer, seller, spread, event.seller_id)
        status = self._ledger._require_res(event.request_id).status
        if status == "consumed":
            if event.kind == "usage_rated":
                return None
            journal = self._ledger.apply_delta(
                request_id=event.request_id,
                buyer_debit=buyer,
                seller_earning=seller,
                spread=spread,
                seller_id=event.seller_id,
                rate_version=rate,
                evidence_digest=event.evidence_digest,
            )
        else:
            journal = self._ledger.settle(
                request_id=event.request_id,
                buyer_debit=buyer,
                seller_earning=seller,
                spread=spread,
                seller_id=event.seller_id,
                rate_version=rate,
                evidence_digest=event.evidence_digest,
            )
        case = self._cases.get(event.request_id)
        if case is not None:
            case.status = "recovered"
            case.updated_at = self._now()
        return journal
