"""Sync SQLAlchemy adapter for Provider Bindings."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Mapping, NoReturn, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.bindings.models import (
    BindingRecord,
    ProviderBindingAuditRow,
    ProviderBindingRow,
    utcnow,
)
from app.domain.bindings.store import PublishConflict

T = TypeVar("T")


def _to_record(row: ProviderBindingRow) -> BindingRecord:
    return BindingRecord(
        binding_id=row.id,
        project_id=row.project_id,
        owner_account_id=row.owner_account_id,
        protocol=row.protocol,
        supply_mode=row.supply_mode,
        status=row.status,
        version=row.version,
        allowed_providers=list(row.allowed_providers or []),
        allowed_models=list(row.allowed_models or []),
        allowed_regions=list(row.allowed_regions or []),
        connection_id=row.connection_id,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_integrity(exc: IntegrityError) -> NoReturn:
    msg = str(exc.orig) if getattr(exc, "orig", None) is not None else str(exc)
    if "uq_bindings_active_protocol" in msg.lower() or "unique" in msg.lower():
        raise PublishConflict from exc
    raise exc


class SQLBindingStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, rec: BindingRecord) -> None:
        self._s.add(
            ProviderBindingRow(
                id=rec.binding_id,
                project_id=rec.project_id,
                owner_account_id=rec.owner_account_id,
                protocol=rec.protocol,
                supply_mode=rec.supply_mode,
                status=rec.status,
                version=rec.version,
                allowed_providers=rec.allowed_providers,
                allowed_models=rec.allowed_models,
                allowed_regions=rec.allowed_regions,
                connection_id=rec.connection_id,
                published_at=rec.published_at,
                created_at=rec.created_at or utcnow(),
                updated_at=rec.updated_at or utcnow(),
            )
        )
        try:
            self._s.flush()
        except IntegrityError as exc:
            _map_integrity(exc)

    def get(self, binding_id: uuid.UUID) -> BindingRecord | None:
        row = self._s.get(ProviderBindingRow, binding_id)
        return _to_record(row) if row is not None else None

    def list_by_project(self, project_id: uuid.UUID) -> list[BindingRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderBindingRow).where(
                    ProviderBindingRow.project_id == project_id
                )
            )
        )
        return [_to_record(r) for r in rows]

    def list_by_project_protocol(
        self, project_id: uuid.UUID, protocol: str
    ) -> list[BindingRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderBindingRow).where(
                    ProviderBindingRow.project_id == project_id,
                    ProviderBindingRow.protocol == protocol,
                )
            )
        )
        return [_to_record(r) for r in rows]

    def save(self, rec: BindingRecord) -> None:
        row = self._s.get(ProviderBindingRow, rec.binding_id)
        if row is None:
            raise KeyError(rec.binding_id)
        row.status = rec.status
        row.version = rec.version
        row.published_at = rec.published_at
        row.updated_at = rec.updated_at or utcnow()
        try:
            self._s.flush()
        except IntegrityError as exc:
            _map_integrity(exc)

    def deactivate_active(self, project_id: uuid.UUID, protocol: str) -> None:
        rows = list(
            self._s.scalars(
                select(ProviderBindingRow).where(
                    ProviderBindingRow.project_id == project_id,
                    ProviderBindingRow.protocol == protocol,
                    ProviderBindingRow.status == "active",
                )
            )
        )
        now = utcnow()
        for row in rows:
            row.status = "inactive"
            row.updated_at = now
        self._s.flush()

    def max_version(self, project_id: uuid.UUID, protocol: str) -> int:
        rows = self.list_by_project_protocol(project_id, protocol)
        if not rows:
            return 0
        return max(r.version for r in rows)

    def list_by_connection(self, connection_id: uuid.UUID) -> list[BindingRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderBindingRow).where(
                    ProviderBindingRow.connection_id == connection_id
                )
            )
        )
        return [_to_record(r) for r in rows]

    def publish_atomic(self, rec: BindingRecord) -> None:
        self.deactivate_active(rec.project_id, rec.protocol)
        self.save(rec)

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
        self._s.add(
            ProviderBindingAuditRow(
                id=uuid.uuid4(),
                owner_account_id=owner_id,
                project_id=project_id,
                binding_id=binding_id,
                event_type=event_type,
                request_id=request_id,
                payload=dict(payload or {}),
                created_at=utcnow(),
            )
        )
        self._s.flush()


class SessionedBindingStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLBindingStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLBindingStore(session))
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

    def create(self, rec: BindingRecord) -> None:
        self._run(lambda s: s.create(rec))

    def get(self, binding_id: uuid.UUID) -> BindingRecord | None:
        return self._run(lambda s: s.get(binding_id))

    def list_by_project(self, project_id: uuid.UUID) -> list[BindingRecord]:
        return self._run(lambda s: s.list_by_project(project_id))

    def list_by_project_protocol(
        self, project_id: uuid.UUID, protocol: str
    ) -> list[BindingRecord]:
        return self._run(lambda s: s.list_by_project_protocol(project_id, protocol))

    def save(self, rec: BindingRecord) -> None:
        self._run(lambda s: s.save(rec))

    def deactivate_active(self, project_id: uuid.UUID, protocol: str) -> None:
        self._run(lambda s: s.deactivate_active(project_id, protocol))

    def max_version(self, project_id: uuid.UUID, protocol: str) -> int:
        return self._run(lambda s: s.max_version(project_id, protocol))

    def list_by_connection(self, connection_id: uuid.UUID) -> list[BindingRecord]:
        return self._run(lambda s: s.list_by_connection(connection_id))

    def publish_atomic(self, rec: BindingRecord) -> None:
        self._run(lambda s: s.publish_atomic(rec))

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
        self._run(
            lambda s: s.audit(
                owner_id=owner_id,
                project_id=project_id,
                binding_id=binding_id,
                event_type=event_type,
                request_id=request_id,
                payload=payload,
            )
        )
