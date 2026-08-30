"""Connection persistence port and memory implementation."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping, Protocol

from app.domain.connections.models import (
    CapabilitySnapshot,
    ConnectionRecord,
    utcnow,
)


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

    def save_health(self, rec: ConnectionRecord) -> None: ...

    def list_probe_due(self, now: datetime, limit: int) -> list[ConnectionRecord]: ...

    def save_snapshot(
        self,
        *,
        connection_id: uuid.UUID,
        version: int,
        capabilities: list[Mapping[str, Any]] | list[dict[str, Any]],
    ) -> None: ...

    def list_snapshots(self, connection_id: uuid.UUID) -> list[CapabilitySnapshot]: ...

    def max_snapshot_version(self, connection_id: uuid.UUID) -> int: ...

    def save_lifecycle(self, rec: ConnectionRecord, expected_state: str) -> None: ...

    def list_all_active(self) -> list[ConnectionRecord]: ...


class MemoryConnectionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_id: dict[uuid.UUID, ConnectionRecord] = {}
        self.audits: list[dict[str, object]] = []
        self.snapshots: dict[uuid.UUID, list[dict[str, Any]]] = {}

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

    def save_health(self, rec: ConnectionRecord) -> None:
        with self._lock:
            cur = self.by_id.get(rec.connection_id)
            if cur is None:
                raise KeyError(rec.connection_id)
            cur.health_state = rec.health_state
            cur.health_reason = rec.health_reason
            cur.health_checked_at = rec.health_checked_at
            cur.consecutive_successes = rec.consecutive_successes
            cur.consecutive_failures = rec.consecutive_failures
            cur.last_probe_at = rec.last_probe_at
            cur.next_probe_at = rec.next_probe_at
            cur.capability_version = rec.capability_version
            cur.updated_at = rec.updated_at or utcnow()

    def list_probe_due(self, now: datetime, limit: int) -> list[ConnectionRecord]:
        with self._lock:
            due = [
                deepcopy(r)
                for r in self.by_id.values()
                if r.status == "active"
                and r.deleted_at is None
                and (r.next_probe_at is None or r.next_probe_at <= now)
            ]
            due.sort(key=lambda r: r.next_probe_at or now)
            return due[: max(0, limit)]

    def save_snapshot(
        self,
        *,
        connection_id: uuid.UUID,
        version: int,
        capabilities: list[Mapping[str, Any]] | list[dict[str, Any]],
    ) -> None:
        with self._lock:
            self.snapshots.setdefault(connection_id, []).append(
                {
                    "connection_id": connection_id,
                    "version": version,
                    "capabilities": [dict(c) for c in capabilities],
                    "created_at": utcnow(),
                }
            )

    def list_snapshots(self, connection_id: uuid.UUID) -> list[CapabilitySnapshot]:
        with self._lock:
            rows = self.snapshots.get(connection_id) or []
            return [
                CapabilitySnapshot(
                    connection_id=r["connection_id"],
                    version=int(r["version"]),
                    capabilities=list(r["capabilities"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def max_snapshot_version(self, connection_id: uuid.UUID) -> int:
        with self._lock:
            rows = self.snapshots.get(connection_id) or []
            if not rows:
                return 0
            return max(int(r["version"]) for r in rows)

    def save_lifecycle(self, rec: ConnectionRecord, expected_state: str) -> None:
        with self._lock:
            cur = self.by_id.get(rec.connection_id)
            if cur is None:
                raise KeyError(rec.connection_id)
            if cur.lifecycle_state != expected_state:
                raise VersionConflict
            cur.lifecycle_state = rec.lifecycle_state
            cur.supply_mode = rec.supply_mode
            cur.updated_at = rec.updated_at or utcnow()

    def list_all_active(self) -> list[ConnectionRecord]:
        with self._lock:
            return [
                deepcopy(r)
                for r in self.by_id.values()
                if r.status == "active" and r.deleted_at is None
            ]
