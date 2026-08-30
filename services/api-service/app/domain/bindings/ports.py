"""Connection and price ports (SF14/SF27 supply real implementations later)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.domain.endpcatalog import CatalogError, load_catalog


@dataclass(frozen=True)
class ConnectionFact:
    connection_id: uuid.UUID
    provider: str
    supply_mode: str
    usable: bool


class ConnectionLookup(Protocol):
    def get(self, connection_id: uuid.UUID) -> ConnectionFact | None: ...


class EmptyConnectionLookup:
    def get(self, connection_id: uuid.UUID) -> ConnectionFact | None:
        return None


class DictConnectionLookup:
    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, ConnectionFact] = {}

    def put(self, fact: ConnectionFact) -> None:
        self._rows[fact.connection_id] = fact

    def mark_unusable(self, connection_id: uuid.UUID) -> None:
        cur = self._rows.get(connection_id)
        if cur is not None:
            self._rows[connection_id] = ConnectionFact(
                connection_id=cur.connection_id,
                provider=cur.provider,
                supply_mode=cur.supply_mode,
                usable=False,
            )

    def get(self, connection_id: uuid.UUID) -> ConnectionFact | None:
        return self._rows.get(connection_id)


class PriceAvailability(Protocol):
    def available(self, protocol: str) -> bool: ...


class CatalogPriceLookup:
    """Stable non-control-plane catalog records stand in until SF27 rates exist."""

    def available(self, protocol: str) -> bool:
        try:
            data = load_catalog()
        except CatalogError:
            return False
        records = data.get("records") or []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            if rec.get("provider") != protocol:
                continue
            if rec.get("stability") != "stable":
                continue
            tags = rec.get("capability_tags") or []
            if "control_plane" in tags or rec.get("stability") == "control_plane":
                continue
            return True
        return False


class AlwaysPriceLookup:
    def available(self, protocol: str) -> bool:
        return protocol in {"openai", "anthropic", "vertex"}
