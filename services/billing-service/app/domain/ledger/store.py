"""Append-only in-memory ledger. Published entries cannot be mutated."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Protocol

from app.domain.ledger.errors import IMMUTABLE_ENTRY, MSG, LedgerError
from app.domain.ledger.models import Entry, Reservation


class LedgerStore(Protocol):
    def append(self, entry: Entry) -> None: ...

    def list_entries(self) -> list[Entry]: ...

    def entries_for(self, account_id: str) -> list[Entry]: ...

    def put_reservation(self, rec: Reservation) -> None: ...

    def get_reservation(self, request_id: str) -> Reservation | None: ...

    def get_by_idempotency(self, key: str) -> Reservation | None: ...

    def save_reservation(self, rec: Reservation) -> None: ...

    def list_reservations(self) -> list[Reservation]: ...

    def mutate_entry(self, entry_id: str) -> None: ...

    def delete_entry(self, entry_id: str) -> None: ...


class MemoryLedgerStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.entries: list[Entry] = []
        self.reservations: dict[str, Reservation] = {}
        self.by_idempotency: dict[str, str] = {}

    def append(self, entry: Entry) -> None:
        with self._lock:
            self.entries.append(deepcopy(entry))

    def list_entries(self) -> list[Entry]:
        with self._lock:
            return [deepcopy(e) for e in self.entries]

    def entries_for(self, account_id: str) -> list[Entry]:
        with self._lock:
            return [deepcopy(e) for e in self.entries if e.account_id == account_id]

    def put_reservation(self, rec: Reservation) -> None:
        with self._lock:
            self.reservations[rec.request_id] = deepcopy(rec)
            self.by_idempotency[rec.idempotency_key] = rec.request_id

    def get_reservation(self, request_id: str) -> Reservation | None:
        with self._lock:
            rec = self.reservations.get(request_id)
            return deepcopy(rec) if rec is not None else None

    def get_by_idempotency(self, key: str) -> Reservation | None:
        with self._lock:
            rid = self.by_idempotency.get(key)
            if rid is None:
                return None
            rec = self.reservations.get(rid)
            return deepcopy(rec) if rec is not None else None

    def save_reservation(self, rec: Reservation) -> None:
        with self._lock:
            if rec.request_id not in self.reservations:
                raise KeyError(rec.request_id)
            self.reservations[rec.request_id] = deepcopy(rec)

    def list_reservations(self) -> list[Reservation]:
        with self._lock:
            return [deepcopy(r) for r in self.reservations.values()]

    def mutate_entry(self, entry_id: str) -> None:
        raise LedgerError(IMMUTABLE_ENTRY, MSG[IMMUTABLE_ENTRY])

    def delete_entry(self, entry_id: str) -> None:
        raise LedgerError(IMMUTABLE_ENTRY, MSG[IMMUTABLE_ENTRY])

    def locked(self) -> threading.RLock:
        return self._lock
