"""Immutable ledger records. Amounts are integer test-quota minor units."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Direction = Literal["debit", "credit"]
EntryStatus = Literal["reserved", "settled", "released", "unresolved", "reversed"]
AccountKind = Literal[
    "buyer_quota",
    "project_quota",
    "key_quota",
    "seller_earning",
    "platform_spread",
]
ReservationStatus = Literal["held", "consumed", "released", "unresolved"]
UNIT = "test_quota"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def account_id_for(kind: AccountKind, raw: str) -> str:
    return f"{kind}:{raw}"


@dataclass(frozen=True)
class Entry:
    entry_id: str
    journal_id: str
    account_id: str
    account_kind: AccountKind
    request_id: str
    amount_minor_units: int
    direction: Direction
    status: EntryStatus
    rate_version: str
    created_at: datetime
    project_id: str | None = None
    key_id: str | None = None
    evidence_digest: str | None = None
    idempotency_key: str | None = None
    reverses_entry_id: str | None = None
    unit: str = UNIT


@dataclass
class Reservation:
    reservation_id: str
    request_id: str
    idempotency_key: str
    account_id: str
    project_id: str
    key_id: str
    amount_minor: int
    remaining_minor: int
    status: ReservationStatus
    rate_version: str
    journal_id: str
    created_at: datetime
    unresolved_reason: str | None = None


@dataclass(frozen=True)
class Balance:
    account_id: str
    available: int
    reserved: int
    settled_debit: int
    settled_credit: int


@dataclass
class Journal:
    journal_id: str
    request_id: str
    entry_ids: list[str] = field(default_factory=list)
