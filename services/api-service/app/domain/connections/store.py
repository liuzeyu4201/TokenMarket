"""Connection persistence port and memory implementation."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from typing import Any, Mapping, Protocol

from app.domain.connections.models import ConnectionRecord, utcnow


class VersionConflict(Exception):
    pass


class ConnectionStore(Protocol):
    def create(self, rec: ConnectionRecord) -> None: ...

    def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None: ...

    def list_by_seller(self, seller_id: uuid.UUID) -> list[ConnectionRecord]: ...

    def save_replace(self, rec: ConnectionRecord, expected_version: int) -> None: ...

    def audit(
        self,
        *,
        seller_id: uuid.UUID,
        connection_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None: ...


class MemoryConnectionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_id: dict[uuid.UUID, ConnectionRecord] = {}
        self.audits: list[dict[str, object]] = []

    def create(self, rec: ConnectionRecord) -> None:
        with self._lock:
            stored = deepcopy(rec)
            self.by_id[rec.connection_id] = stored

    def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        with self._lock:
            rec = self.by_id.get(connection_id)
            return deepcopy(rec) if rec is not None else None

    def list_by_seller(self, seller_id: uuid.UUID) -> list[ConnectionRecord]:
        with self._lock:
            return [
                deepcopy(r)
                for r in self.by_id.values()
                if r.seller_account_id == seller_id and r.status != "deleted"
            ]

    def save_replace(self, rec: ConnectionRecord, expected_version: int) -> None:
        with self._lock:
            cur = self.by_id.get(rec.connection_id)
            if cur is None:
                raise KeyError(rec.connection_id)
            if cur.credential_version != expected_version:
                raise VersionConflict
            self.by_id[rec.connection_id] = deepcopy(rec)

    def audit(
        self,
        *,
        seller_id: uuid.UUID,
        connection_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.audits.append(
                {
                    "seller_id": str(seller_id),
                    "connection_id": str(connection_id) if connection_id else None,
                    "event_type": event_type,
                    "request_id": request_id,
                    "payload": dict(payload or {}),
                    "created_at": utcnow().isoformat(),
                }
            )
