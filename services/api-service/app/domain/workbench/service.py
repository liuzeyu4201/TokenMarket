"""Seller quote workbench: append-only quotes, capacity, audit, privacy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkbenchError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class PlatformBounds:
    buyer_multiplier_bps: int = 12000
    seller_quote_min_bps: int = 8000
    seller_quote_max_bps: int = 11000
    rate_version: str = "rv-published"


@dataclass
class QuoteRevision:
    seq: int
    multiplier_bps: int
    rate_version: str
    created_at: datetime
    actor_id: str


@dataclass
class AuditEvent:
    actor_id: str
    action: str
    connection_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


@dataclass
class Earnings:
    settled_minor: int = 0
    unresolved_count: int = 0
    unresolved_reasons: list[str] = field(default_factory=list)
    ledger_ready: bool = False


@dataclass
class ConnectionSnapshot:
    connection_id: str
    seller_account_id: str
    provider: str
    supply_mode: str
    lifecycle_state: str
    health_state: str
    health_reason: str | None = None


class WorkbenchService:
    def __init__(
        self,
        bounds: PlatformBounds | None = None,
        *,
        quote_limit: int = 10,
        quote_window_s: float = 60.0,
    ) -> None:
        self.bounds = bounds or PlatformBounds()
        self.quote_limit = quote_limit
        self.quote_window_s = quote_window_s
        self._mu = threading.Lock()
        self._quotes: dict[str, list[QuoteRevision]] = {}
        self._capacity: dict[str, int] = {}
        self._audit: list[AuditEvent] = []
        self._earnings: dict[str, Earnings] = {}
        self._quote_times: dict[str, list[float]] = {}

    def submit_quote(
        self,
        *,
        seller_id: str,
        connection_id: str,
        multiplier_bps: int,
        actor_id: str,
        owner_id: str,
    ) -> QuoteRevision:
        if owner_id != seller_id:
            raise WorkbenchError("FORBIDDEN", "不能为他人连接报价", 403)
        b = self.bounds
        if (
            multiplier_bps < b.seller_quote_min_bps
            or multiplier_bps > b.seller_quote_max_bps
        ):
            raise WorkbenchError("QUOTE_OUT_OF_BOUNDS", "报价超出平台上下界")
        if multiplier_bps > b.buyer_multiplier_bps:
            raise WorkbenchError("NEGATIVE_SPREAD", "报价会导致负平台价差")
        with self._mu:
            self._rate_limit(seller_id)
            hist = self._quotes.setdefault(connection_id, [])
            before = hist[-1].multiplier_bps if hist else None
            rev = QuoteRevision(
                seq=len(hist) + 1,
                multiplier_bps=multiplier_bps,
                rate_version=b.rate_version,
                created_at=utcnow(),
                actor_id=actor_id,
            )
            hist.append(rev)
            self._audit.append(
                AuditEvent(
                    actor_id=actor_id,
                    action="quote",
                    connection_id=connection_id,
                    before={"multiplier_bps": before},
                    after={"multiplier_bps": multiplier_bps, "seq": rev.seq},
                    created_at=rev.created_at,
                )
            )
            return rev

    def set_capacity(
        self,
        *,
        seller_id: str,
        connection_id: str,
        declared_capacity: int,
        actor_id: str,
        owner_id: str,
    ) -> int:
        if owner_id != seller_id:
            raise WorkbenchError("FORBIDDEN", "不能修改他人容量", 403)
        if declared_capacity < 0:
            raise WorkbenchError("INVALID_CAPACITY", "容量不能为负")
        with self._mu:
            before = self._capacity.get(connection_id)
            self._capacity[connection_id] = declared_capacity
            self._audit.append(
                AuditEvent(
                    actor_id=actor_id,
                    action="capacity",
                    connection_id=connection_id,
                    before={"declared_capacity": before},
                    after={"declared_capacity": declared_capacity},
                    created_at=utcnow(),
                )
            )
            return declared_capacity

    def record_unresolved(self, connection_id: str, reason: str) -> None:
        with self._mu:
            earn = self._earnings.setdefault(connection_id, Earnings())
            earn.unresolved_count += 1
            if reason not in earn.unresolved_reasons:
                earn.unresolved_reasons.append(reason)

    def record_settled(self, connection_id: str, minor: int) -> None:
        if minor < 0:
            raise WorkbenchError("INVALID_EARNING", "结算不能为负")
        with self._mu:
            earn = self._earnings.setdefault(connection_id, Earnings())
            earn.settled_minor += minor
            earn.ledger_ready = True

    def card(self, snap: ConnectionSnapshot, seller_id: str) -> dict[str, Any]:
        if snap.seller_account_id != seller_id:
            raise WorkbenchError("FORBIDDEN", "不能查看他人连接", 403)
        with self._mu:
            hist = list(self._quotes.get(snap.connection_id, []))
            cap = self._capacity.get(snap.connection_id)
            earn = self._earnings.get(snap.connection_id) or Earnings()
            current = hist[-1] if hist else None
        admits = self.admits_new(snap.lifecycle_state, cap)
        public = {
            "connection_id": snap.connection_id,
            "provider": snap.provider,
            "supply_mode": snap.supply_mode,
            "lifecycle_state": snap.lifecycle_state,
            "health_state": snap.health_state,
            "health_reason": snap.health_reason,
            "declared_capacity": cap,
            "admits_new": admits,
            "quote": (
                None
                if current is None
                else {
                    "seq": current.seq,
                    "multiplier_bps": current.multiplier_bps,
                    "rate_version": current.rate_version,
                }
            ),
            "quote_history_len": len(hist),
            "bounds": {
                "seller_quote_min_bps": self.bounds.seller_quote_min_bps,
                "seller_quote_max_bps": self.bounds.seller_quote_max_bps,
                "rate_version": self.bounds.rate_version,
            },
            "earnings": {
                "settled_minor": earn.settled_minor,
                "unresolved_count": earn.unresolved_count,
                "unresolved_reasons": list(earn.unresolved_reasons),
                "ledger_ready": earn.ledger_ready,
            },
            "route_summary": {
                "admits_new": admits,
                "reason": None if admits else "paused_or_zero_capacity_or_lifecycle",
            },
        }
        self._assert_private(public)
        return public

    def history(
        self, connection_id: str, seller_id: str, owner_id: str
    ) -> list[dict[str, Any]]:
        if owner_id != seller_id:
            raise WorkbenchError("FORBIDDEN", "不能查看他人历史", 403)
        with self._mu:
            hist = list(self._quotes.get(connection_id, []))
        return [
            {
                "seq": r.seq,
                "multiplier_bps": r.multiplier_bps,
                "rate_version": r.rate_version,
                "created_at": r.created_at.isoformat(),
            }
            for r in hist
        ]

    def audits(self, connection_id: str) -> list[AuditEvent]:
        with self._mu:
            return [e for e in self._audit if e.connection_id == connection_id]

    def admits_new(self, lifecycle_state: str, declared_capacity: int | None) -> bool:
        if lifecycle_state in {"paused", "draining", "retired", "draft"}:
            return False
        if declared_capacity is not None and declared_capacity <= 0:
            return False
        return lifecycle_state in {"listed", "bound", "verified"}

    def _rate_limit(self, seller_id: str) -> None:
        now = time.monotonic()
        window = self._quote_times.setdefault(seller_id, [])
        window[:] = [t for t in window if now - t < self.quote_window_s]
        if len(window) >= self.quote_limit:
            raise WorkbenchError("RATE_LIMITED", "报价更新过于频繁", 429)
        window.append(now)

    def _assert_private(self, public: dict[str, Any]) -> None:
        blob = str(public).lower()
        for banned in (
            "buyer_multiplier",
            "buyer_id",
            "raw_body",
            "spread",
            "platform_profit",
        ):
            if banned in blob:
                raise WorkbenchError("PRIVACY", "工作台泄漏禁止字段", 500)
