"""Recon cases, tickets, and evidence events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domain.ledger.models import utcnow

ReasonCode = Literal[
    "MISSING_AMOUNT", "MISSING_USAGE", "PARSE_FAILED", "ASYNC_INCOMPLETE"
]
NextAction = Literal["wait_callback", "retry", "manual"]
CaseStatus = Literal["open", "recovered", "manual"]
EventKind = Literal[
    "reported_cost",
    "usage_rated",
    "parse_failed",
    "async_pending",
    "missing_amount",
    "missing_usage",
]
TicketKind = Literal["VARIANCE", "ORPHAN", "UNBALANCED"]


@dataclass
class UnresolvedCase:
    request_id: str
    reason_code: ReasonCode
    amount_exposure_minor: int
    next_action: NextAction
    owner: str
    status: CaseStatus
    missing_evidence: str = ""
    retry_at: datetime | None = None
    sla_until: datetime | None = None
    connection_id: str = ""
    rate_version: str = ""
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class EvidenceEvent:
    event_id: str
    request_id: str
    kind: EventKind
    buyer_debit: int | None = None
    seller_earning: int | None = None
    spread: int | None = None
    seller_id: str = "seller-1"
    rate_version: str | None = None
    evidence_digest: str = ""
    connection_id: str = ""
    computed_buyer: int | None = None


@dataclass
class ReconTicket:
    ticket_id: str
    kind: TicketKind
    request_id: str
    detail: str
    created_at: datetime
    reported_minor: int | None = None
    computed_minor: int | None = None


@dataclass
class ReversePreview:
    preview_id: str
    request_id: str
    original_entry_ids: list[str]
    net_buyer_delta: int


@dataclass
class DailyReport:
    balanced: bool
    orphan_request_ids: list[str]
    ticket_count: int
    open_unresolved: int
    aggregate_matches_detail: bool
