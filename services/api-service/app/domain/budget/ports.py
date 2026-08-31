"""Ledger projection port for buyer budget views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class UsageRow:
    request_id: str
    key_id: str
    status: str
    amount_minor: int
    reason: str | None = None
    protocol: str | None = None


@dataclass
class QuotaView:
    available: int
    reserved: int
    settled: int
    unresolved: int
    requests: list[UsageRow] = field(default_factory=list)


class LedgerView(Protocol):
    def overview(self, project_id: str) -> QuotaView: ...


class MemoryLedgerView:
    def __init__(self) -> None:
        self.views: dict[str, QuotaView] = {}

    def put(self, project_id: str, view: QuotaView) -> None:
        self.views[project_id] = view

    def overview(self, project_id: str) -> QuotaView:
        return self.views.get(
            project_id,
            QuotaView(available=0, reserved=0, settled=0, unresolved=0),
        )
