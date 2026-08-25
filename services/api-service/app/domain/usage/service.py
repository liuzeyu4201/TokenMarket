"""SF17 usage observation persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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


class UsageStore(Protocol):
    def get(self, request_id: str) -> UsageRecord | None: ...

    def insert(self, rec: UsageRecord) -> None: ...

    def add_conflict(self, request_id: str, reason: str) -> None: ...


class MemoryUsageStore:
    def __init__(self) -> None:
        self.by_id: dict[str, UsageRecord] = {}
        self.conflicts: list[tuple[str, str]] = []

    def get(self, request_id: str) -> UsageRecord | None:
        return self.by_id.get(request_id)

    def insert(self, rec: UsageRecord) -> None:
        self.by_id[rec.request_id] = rec

    def add_conflict(self, request_id: str, reason: str) -> None:
        self.conflicts.append((request_id, reason))


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
        self._store.insert(rec)
        self.rows.append(rec)
        return rec


def _conflict(a: UsageRecord, b: UsageRecord) -> bool:
    return (
        a.platform != b.platform
        or a.model != b.model
        or a.total_tokens != b.total_tokens
        or a.source != b.source
    )
