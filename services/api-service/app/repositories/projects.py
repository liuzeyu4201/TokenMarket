"""Sync SQLAlchemy adapter for buyer Projects."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Mapping, NoReturn, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.projects.models import (
    DeletionBlocker,
    ProjectAuditEventRow,
    ProjectIdempotencyRow,
    ProjectProtocolRow,
    ProjectRecord,
    ProjectRow,
    ProjectRuntimeBlockerRow,
    ProtocolState,
    utcnow,
)
from app.domain.projects.store import NameConflict

T = TypeVar("T")


def _to_record(row: ProjectRow, protocols: list[ProjectProtocolRow]) -> ProjectRecord:
    return ProjectRecord(
        project_id=row.id,
        owner_account_id=row.owner_account_id,
        display_name=row.display_name,
        name_normalized=row.name_normalized,
        mode=row.mode,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
        deleted_at=row.deleted_at,
        preview_opt_in=bool(getattr(row, "preview_opt_in", False)),
        protocols=[
            ProtocolState(
                protocol=p.protocol,
                enabled=p.enabled,
                enabled_at=p.enabled_at,
                disabled_at=p.disabled_at,
            )
            for p in protocols
        ],
    )


def _map_integrity(exc: IntegrityError) -> NoReturn:
    msg = str(exc.orig) if getattr(exc, "orig", None) is not None else str(exc)
    lowered = msg.lower()
    if "mode is immutable" in lowered:
        raise RuntimeError("project mode is immutable") from exc
    if "uq_projects_owner_name_live" in lowered or "unique" in lowered:
        raise NameConflict from exc
    raise exc


class SQLProjectStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _protocols(self, project_id: uuid.UUID) -> list[ProjectProtocolRow]:
        return list(
            self._s.scalars(
                select(ProjectProtocolRow).where(
                    ProjectProtocolRow.project_id == project_id
                )
            )
        )

    def create(self, rec: ProjectRecord) -> None:
        self._s.add(
            ProjectRow(
                id=rec.project_id,
                owner_account_id=rec.owner_account_id,
                display_name=rec.display_name,
                name_normalized=rec.name_normalized,
                mode=rec.mode,
                status=rec.status,
                created_at=rec.created_at,
                updated_at=rec.updated_at,
                archived_at=rec.archived_at,
                deleted_at=rec.deleted_at,
                preview_opt_in=bool(rec.preview_opt_in),
            )
        )
        try:
            self._s.flush()
        except IntegrityError as exc:
            _map_integrity(exc)
        for proto in rec.protocols:
            self._s.add(
                ProjectProtocolRow(
                    project_id=rec.project_id,
                    protocol=proto.protocol,
                    enabled=proto.enabled,
                    enabled_at=proto.enabled_at,
                    disabled_at=proto.disabled_at,
                )
            )
        try:
            self._s.flush()
        except IntegrityError as exc:
            _map_integrity(exc)

    def get(self, project_id: uuid.UUID) -> ProjectRecord | None:
        row = self._s.get(ProjectRow, project_id)
        if row is None:
            return None
        return _to_record(row, self._protocols(project_id))

    def list_by_owner(self, owner_id: uuid.UUID) -> list[ProjectRecord]:
        rows = list(
            self._s.scalars(
                select(ProjectRow).where(
                    ProjectRow.owner_account_id == owner_id,
                    ProjectRow.deleted_at.is_(None),
                )
            )
        )
        return [_to_record(r, self._protocols(r.id)) for r in rows]

    def save(self, rec: ProjectRecord) -> None:
        row = self._s.get(ProjectRow, rec.project_id)
        if row is None:
            raise KeyError(rec.project_id)
        row.display_name = rec.display_name
        row.name_normalized = rec.name_normalized
        # mode is never assigned — trigger still guards raw SQL / mistakes
        row.status = rec.status
        row.updated_at = rec.updated_at
        row.archived_at = rec.archived_at
        row.deleted_at = rec.deleted_at
        row.preview_opt_in = bool(rec.preview_opt_in)
        existing = {p.protocol: p for p in self._protocols(rec.project_id)}
        for proto in rec.protocols:
            cur = existing.get(proto.protocol)
            if cur is None:
                self._s.add(
                    ProjectProtocolRow(
                        project_id=rec.project_id,
                        protocol=proto.protocol,
                        enabled=proto.enabled,
                        enabled_at=proto.enabled_at,
                        disabled_at=proto.disabled_at,
                    )
                )
            else:
                cur.enabled = proto.enabled
                cur.enabled_at = proto.enabled_at
                cur.disabled_at = proto.disabled_at
        try:
            self._s.flush()
        except IntegrityError as exc:
            _map_integrity(exc)

    def blockers(self, project_id: uuid.UUID) -> list[DeletionBlocker]:
        rows = list(
            self._s.scalars(
                select(ProjectRuntimeBlockerRow).where(
                    ProjectRuntimeBlockerRow.project_id == project_id,
                    ProjectRuntimeBlockerRow.resolved_at.is_(None),
                )
            )
        )
        return [
            DeletionBlocker(
                kind=r.kind,
                reference_id=r.reference_id,
                blocker_id=r.id,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]

    def add_blocker(
        self, project_id: uuid.UUID, kind: str, reference_id: str
    ) -> uuid.UUID:
        bid = uuid.uuid4()
        self._s.add(
            ProjectRuntimeBlockerRow(
                id=bid,
                project_id=project_id,
                kind=kind,
                reference_id=reference_id,
                created_at=utcnow(),
            )
        )
        self._s.flush()
        return bid

    def get_idempotency(
        self, owner_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        row = self._s.get(ProjectIdempotencyRow, (owner_id, key))
        if row is None:
            return None
        return row.request_hash, row.project_id

    def put_idempotency(
        self,
        owner_id: uuid.UUID,
        key: str,
        digest: str,
        project_id: uuid.UUID | None,
    ) -> None:
        row = self._s.get(ProjectIdempotencyRow, (owner_id, key))
        if row is None:
            self._s.add(
                ProjectIdempotencyRow(
                    owner_account_id=owner_id,
                    idempotency_key=key,
                    request_hash=digest,
                    project_id=project_id,
                    created_at=utcnow(),
                )
            )
        else:
            row.request_hash = digest
            row.project_id = project_id
        self._s.flush()

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._s.add(
            ProjectAuditEventRow(
                id=uuid.uuid4(),
                owner_account_id=owner_id,
                project_id=project_id,
                event_type=event_type,
                request_id=request_id,
                payload=dict(payload or {}),
                created_at=utcnow(),
            )
        )
        self._s.flush()


class SessionedProjectStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLProjectStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLProjectStore(session))
            session.commit()
            return out
        except IntegrityError as exc:
            session.rollback()
            _map_integrity(exc)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create(self, rec: ProjectRecord) -> None:
        self._run(lambda s: s.create(rec))

    def get(self, project_id: uuid.UUID) -> ProjectRecord | None:
        return self._run(lambda s: s.get(project_id))

    def list_by_owner(self, owner_id: uuid.UUID) -> list[ProjectRecord]:
        return self._run(lambda s: s.list_by_owner(owner_id))

    def save(self, rec: ProjectRecord) -> None:
        self._run(lambda s: s.save(rec))

    def blockers(self, project_id: uuid.UUID) -> list[DeletionBlocker]:
        return self._run(lambda s: s.blockers(project_id))

    def add_blocker(
        self, project_id: uuid.UUID, kind: str, reference_id: str
    ) -> uuid.UUID:
        return self._run(lambda s: s.add_blocker(project_id, kind, reference_id))

    def get_idempotency(
        self, owner_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        return self._run(lambda s: s.get_idempotency(owner_id, key))

    def put_idempotency(
        self,
        owner_id: uuid.UUID,
        key: str,
        digest: str,
        project_id: uuid.UUID | None,
    ) -> None:
        self._run(lambda s: s.put_idempotency(owner_id, key, digest, project_id))

    def audit(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._run(
            lambda s: s.audit(
                owner_id=owner_id,
                project_id=project_id,
                event_type=event_type,
                request_id=request_id,
                payload=payload,
            )
        )
