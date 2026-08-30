"""Project persistence port and memory implementation."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from typing import Any, Mapping, Protocol

from app.domain.projects.models import DeletionBlocker, ProjectRecord, utcnow


class NameConflict(Exception):
    """Owner already has a live Project with this normalized name."""


class ProjectStore(Protocol):
    def create(self, rec: ProjectRecord) -> None: ...

    def get(self, project_id: uuid.UUID) -> ProjectRecord | None: ...

    def list_by_owner(self, owner_id: uuid.UUID) -> list[ProjectRecord]: ...

    def save(self, rec: ProjectRecord) -> None: ...

    def blockers(self, project_id: uuid.UUID) -> list[DeletionBlocker]: ...

    def add_blocker(
        self, project_id: uuid.UUID, kind: str, reference_id: str
    ) -> uuid.UUID: ...

    def get_idempotency(
        self, owner_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None: ...

    def put_idempotency(
        self,
        owner_id: uuid.UUID,
        key: str,
        digest: str,
        project_id: uuid.UUID | None,
    ) -> None: ...

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None: ...


class MemoryProjectStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_id: dict[uuid.UUID, ProjectRecord] = {}
        self._blockers: dict[uuid.UUID, list[DeletionBlocker]] = {}
        self._idem: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID | None]] = {}
        self.audits: list[dict[str, object]] = []

    def create(self, rec: ProjectRecord) -> None:
        with self._lock:
            for existing in self.by_id.values():
                if (
                    existing.owner_account_id == rec.owner_account_id
                    and existing.name_normalized == rec.name_normalized
                    and existing.deleted_at is None
                ):
                    raise NameConflict
            self.by_id[rec.project_id] = deepcopy(rec)

    def get(self, project_id: uuid.UUID) -> ProjectRecord | None:
        with self._lock:
            rec = self.by_id.get(project_id)
            return deepcopy(rec) if rec is not None else None

    def list_by_owner(self, owner_id: uuid.UUID) -> list[ProjectRecord]:
        with self._lock:
            return [
                deepcopy(r)
                for r in self.by_id.values()
                if r.owner_account_id == owner_id and r.deleted_at is None
            ]

    def save(self, rec: ProjectRecord) -> None:
        with self._lock:
            if rec.project_id not in self.by_id:
                raise KeyError(rec.project_id)
            current = self.by_id[rec.project_id]
            if rec.mode != current.mode:
                raise RuntimeError("project mode is immutable")
            if rec.deleted_at is None:
                for existing in self.by_id.values():
                    if existing.project_id == rec.project_id:
                        continue
                    if (
                        existing.owner_account_id == rec.owner_account_id
                        and existing.name_normalized == rec.name_normalized
                        and existing.deleted_at is None
                    ):
                        raise NameConflict
            self.by_id[rec.project_id] = deepcopy(rec)

    def blockers(self, project_id: uuid.UUID) -> list[DeletionBlocker]:
        with self._lock:
            return [
                deepcopy(b)
                for b in self._blockers.get(project_id, [])
                if b.resolved_at is None
            ]

    def add_blocker(
        self, project_id: uuid.UUID, kind: str, reference_id: str
    ) -> uuid.UUID:
        bid = uuid.uuid4()
        with self._lock:
            self._blockers.setdefault(project_id, []).append(
                DeletionBlocker(
                    kind=kind,
                    reference_id=reference_id,
                    blocker_id=bid,
                )
            )
        return bid

    def get_idempotency(
        self, owner_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        with self._lock:
            return self._idem.get((owner_id, key))

    def put_idempotency(
        self,
        owner_id: uuid.UUID,
        key: str,
        digest: str,
        project_id: uuid.UUID | None,
    ) -> None:
        with self._lock:
            self._idem[(owner_id, key)] = (digest, project_id)

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.audits.append(
                {
                    "owner_id": str(owner_id),
                    "project_id": str(project_id) if project_id else None,
                    "event_type": event_type,
                    "request_id": request_id,
                    "payload": dict(payload or {}),
                    "created_at": utcnow().isoformat(),
                }
            )
