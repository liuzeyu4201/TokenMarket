"""Binding persistence port and memory implementation."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from typing import Any, Mapping, Protocol

from app.domain.bindings.models import BindingRecord, utcnow


class PublishConflict(Exception):
    """Partial unique active (project, protocol) violated."""


class BindingStore(Protocol):
    def create(self, rec: BindingRecord) -> None: ...

    def get(self, binding_id: uuid.UUID) -> BindingRecord | None: ...

    def list_by_project(self, project_id: uuid.UUID) -> list[BindingRecord]: ...

    def list_by_project_protocol(
        self, project_id: uuid.UUID, protocol: str
    ) -> list[BindingRecord]: ...

    def save(self, rec: BindingRecord) -> None: ...

    def deactivate_active(self, project_id: uuid.UUID, protocol: str) -> None: ...

    def max_version(self, project_id: uuid.UUID, protocol: str) -> int: ...

    def list_by_connection(self, connection_id: uuid.UUID) -> list[BindingRecord]: ...

    def publish_atomic(self, rec: BindingRecord) -> None: ...

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        binding_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None: ...


class MemoryBindingStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_id: dict[uuid.UUID, BindingRecord] = {}
        self.audits: list[dict[str, object]] = []

    def create(self, rec: BindingRecord) -> None:
        with self._lock:
            if rec.status == "active":
                self._ensure_single_active(rec)
            self.by_id[rec.binding_id] = deepcopy(rec)

    def get(self, binding_id: uuid.UUID) -> BindingRecord | None:
        with self._lock:
            rec = self.by_id.get(binding_id)
            return deepcopy(rec) if rec is not None else None

    def list_by_project(self, project_id: uuid.UUID) -> list[BindingRecord]:
        with self._lock:
            return [
                deepcopy(r) for r in self.by_id.values() if r.project_id == project_id
            ]

    def list_by_project_protocol(
        self, project_id: uuid.UUID, protocol: str
    ) -> list[BindingRecord]:
        with self._lock:
            return [
                deepcopy(r)
                for r in self.by_id.values()
                if r.project_id == project_id and r.protocol == protocol
            ]

    def save(self, rec: BindingRecord) -> None:
        with self._lock:
            if rec.binding_id not in self.by_id:
                raise KeyError(rec.binding_id)
            if rec.status == "active":
                self._ensure_single_active(rec)
            self.by_id[rec.binding_id] = deepcopy(rec)

    def deactivate_active(self, project_id: uuid.UUID, protocol: str) -> None:
        with self._lock:
            for rec in self.by_id.values():
                if (
                    rec.project_id == project_id
                    and rec.protocol == protocol
                    and rec.status == "active"
                ):
                    rec.status = "inactive"
                    rec.updated_at = utcnow()

    def max_version(self, project_id: uuid.UUID, protocol: str) -> int:
        with self._lock:
            versions = [
                r.version
                for r in self.by_id.values()
                if r.project_id == project_id and r.protocol == protocol
            ]
            return max(versions) if versions else 0

    def list_by_connection(self, connection_id: uuid.UUID) -> list[BindingRecord]:
        with self._lock:
            return [
                deepcopy(r)
                for r in self.by_id.values()
                if r.connection_id == connection_id
            ]

    def publish_atomic(self, rec: BindingRecord) -> None:
        with self._lock:
            for other in self.by_id.values():
                if (
                    other.binding_id != rec.binding_id
                    and other.project_id == rec.project_id
                    and other.protocol == rec.protocol
                    and other.status == "active"
                ):
                    other.status = "inactive"
                    other.updated_at = utcnow()
            if rec.binding_id not in self.by_id:
                raise KeyError(rec.binding_id)
            for other in self.by_id.values():
                if (
                    other.binding_id != rec.binding_id
                    and other.project_id == rec.project_id
                    and other.protocol == rec.protocol
                    and other.status == "active"
                ):
                    raise PublishConflict
            self.by_id[rec.binding_id] = deepcopy(rec)

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        binding_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.audits.append(
                {
                    "owner_id": str(owner_id),
                    "project_id": str(project_id) if project_id else None,
                    "binding_id": str(binding_id) if binding_id else None,
                    "event_type": event_type,
                    "request_id": request_id,
                    "payload": dict(payload or {}),
                }
            )

    def _ensure_single_active(self, rec: BindingRecord) -> None:
        for other in self.by_id.values():
            if (
                other.binding_id != rec.binding_id
                and other.project_id == rec.project_id
                and other.protocol == rec.protocol
                and other.status == "active"
            ):
                raise PublishConflict
