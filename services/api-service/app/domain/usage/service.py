"""SF17 usage observation persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


@dataclass
class UsageRecord:
    request_id: str
    buyer_id: uuid.UUID | None
    platform: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    status: str
    source: str
    proxy_key_id: str | None = None
    api_key_id: str | None = None
    seller_id: uuid.UUID | None = None
    partial: bool = False
    latency_ms: int = 0
    status_code: int = 0
    end_reason: str = ""
    created_at: datetime | None = None


class UsageStore(Protocol):
    def get(self, request_id: str) -> UsageRecord | None: ...

    def insert(self, rec: UsageRecord) -> None: ...

    def add_conflict(self, request_id: str, reason: str) -> None: ...

    def purge_before(self, cutoff: datetime) -> int: ...


class MemoryUsageStore:
    def __init__(self) -> None:
        self.by_id: dict[str, UsageRecord] = {}
        self.conflicts: list[tuple[str, str]] = []

    def get(self, request_id: str) -> UsageRecord | None:
        return self.by_id.get(request_id)

    def insert(self, rec: UsageRecord) -> None:
        if rec.created_at is None:
            rec.created_at = datetime.now(timezone.utc)
        self.by_id[rec.request_id] = rec

    def add_conflict(self, request_id: str, reason: str) -> None:
        self.conflicts.append((request_id, reason))

    def purge_before(self, cutoff: datetime) -> int:
        dead = [
            k
            for k, v in self.by_id.items()
            if v.created_at is not None and v.created_at < cutoff
        ]
        for k in dead:
            del self.by_id[k]
        return len(dead)


class UsageRecorder:
    def __init__(self, store: UsageStore | None = None) -> None:
        self._store: UsageStore = store if store is not None else MemoryUsageStore()
        self.rows: list[UsageRecord] = []

    def record(self, rec: UsageRecord) -> UsageRecord:
        if rec.status == "missing":
            if (
                rec.prompt_tokens == 0
                and rec.completion_tokens == 0
                and rec.total_tokens == 0
            ):
                raise ValueError("fake zero usage forbidden")
            rec = UsageRecord(
                request_id=rec.request_id,
                buyer_id=rec.buyer_id,
                platform=rec.platform,
                model=rec.model,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                status="missing",
                source=rec.source if rec.source != "official" else "not_available",
                proxy_key_id=rec.proxy_key_id,
                api_key_id=rec.api_key_id,
                seller_id=rec.seller_id,
                partial=rec.partial,
                latency_ms=rec.latency_ms,
                status_code=rec.status_code,
                end_reason=rec.end_reason,
            )
        existing = self._store.get(rec.request_id)
        if existing is not None:
            if _conflict(existing, rec):
                self._store.add_conflict(rec.request_id, "payload_mismatch")
            return existing
        if rec.created_at is None:
            rec.created_at = datetime.now(timezone.utc)
        self._store.insert(rec)
        self.rows.append(rec)
        return rec

    def purge_expired(
        self, *, now: datetime | None = None, retain_days: int = 30
    ) -> int:
        when = now if now is not None else datetime.now(timezone.utc)
        cutoff = when - timedelta(days=retain_days)
        n = self._store.purge_before(cutoff)
        self.rows = [
            r for r in self.rows if r.created_at is None or r.created_at >= cutoff
        ]
        return n


def _conflict(a: UsageRecord, b: UsageRecord) -> bool:
    return (
        a.platform != b.platform
        or a.model != b.model
        or a.total_tokens != b.total_tokens
        or a.source != b.source
    )
