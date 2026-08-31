"""Request-id correlated hops. Async usage/ledger are links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TraceHop:
    request_id: str
    service: str
    stage: str
    kind: str
    freshness: str
    at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "service": self.service,
            "stage": self.stage,
            "kind": self.kind,
            "freshness": self.freshness,
            "at": self.at.isoformat(),
        }


class TraceLog:
    def __init__(self) -> None:
        self._hops: list[TraceHop] = []

    def append(self, hop: TraceHop) -> None:
        self._hops.append(hop)

    def correlate(self, request_id: str) -> list[TraceHop]:
        order = ("proxy", "route", "upstream", "usage", "ledger")
        found = [h for h in self._hops if h.request_id == request_id]
        by_stage = {h.stage: h for h in found}
        out: list[TraceHop] = []
        for stage in order:
            hop = by_stage.get(stage)
            if hop is not None:
                out.append(hop)
        return out
