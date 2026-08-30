"""Sync SQLAlchemy adapter for Provider Connections."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Mapping, TypeVar

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domain.connections.models import (
    CapabilitySnapshot,
    ConnectionCapabilitySnapshotRow,
    ConnectionRecord,
    ProviderConnectionAuditRow,
    ProviderConnectionRow,
    utcnow,
)
from app.domain.connections.store import VersionConflict

T = TypeVar("T")


def _to_record(row: ProviderConnectionRow) -> ConnectionRecord:
    return ConnectionRecord(
        connection_id=row.id,
        seller_account_id=row.seller_account_id,
        provider=row.provider,
        supply_mode=row.supply_mode,
        auth_type=row.auth_type,
        base_url=row.base_url,
        region=row.region,
        purpose=row.purpose,
        project_number=row.project_number,
        location=row.location,
        nonce=row.nonce,
        ciphertext=row.ciphertext,
        tag=row.tag,
        key_version=row.key_version,
        credential_fingerprint=row.credential_fingerprint,
        credential_version=row.credential_version,
        status=row.status,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        health_state=row.health_state,
        health_reason=row.health_reason,
        health_checked_at=row.health_checked_at,
        consecutive_successes=row.consecutive_successes,
        consecutive_failures=row.consecutive_failures,
        last_probe_at=row.last_probe_at,
        next_probe_at=row.next_probe_at,
        capability_version=row.capability_version,
        lifecycle_state=row.lifecycle_state,
    )


class SQLConnectionStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, rec: ConnectionRecord) -> None:
        self._s.add(
            ProviderConnectionRow(
                id=rec.connection_id,
                seller_account_id=rec.seller_account_id,
                provider=rec.provider,
                supply_mode=rec.supply_mode,
                auth_type=rec.auth_type,
                base_url=rec.base_url,
                region=rec.region,
                purpose=rec.purpose,
                project_number=rec.project_number,
                location=rec.location,
                nonce=rec.nonce,
                ciphertext=rec.ciphertext,
                tag=rec.tag,
                key_version=rec.key_version,
                credential_fingerprint=rec.credential_fingerprint,
                credential_version=rec.credential_version,
                status=rec.status,
                deleted_at=rec.deleted_at,
                created_at=rec.created_at or utcnow(),
                updated_at=rec.updated_at or utcnow(),
                health_state=rec.health_state,
                health_reason=rec.health_reason,
                health_checked_at=rec.health_checked_at,
                consecutive_successes=rec.consecutive_successes,
                consecutive_failures=rec.consecutive_failures,
                last_probe_at=rec.last_probe_at,
                next_probe_at=rec.next_probe_at,
                capability_version=rec.capability_version,
                lifecycle_state=rec.lifecycle_state,
            )
        )
        self._s.flush()

    def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        row = self._s.get(ProviderConnectionRow, connection_id)
        return _to_record(row) if row is not None else None

    def list_by_seller(self, seller_id: uuid.UUID) -> list[ConnectionRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderConnectionRow)
                .where(
                    ProviderConnectionRow.seller_account_id == seller_id,
                    ProviderConnectionRow.status != "deleted",
                )
                .order_by(ProviderConnectionRow.created_at.desc())
            )
        )
        return [_to_record(r) for r in rows]

    def save_replace(self, rec: ConnectionRecord, expected_version: int) -> None:
        result = self._s.execute(
            update(ProviderConnectionRow)
            .where(
                ProviderConnectionRow.id == rec.connection_id,
                ProviderConnectionRow.credential_version == expected_version,
            )
            .values(
                nonce=rec.nonce,
                ciphertext=rec.ciphertext,
                tag=rec.tag,
                key_version=rec.key_version,
                credential_fingerprint=rec.credential_fingerprint,
                credential_version=rec.credential_version,
                project_number=rec.project_number,
                location=rec.location,
                region=rec.region,
                status=rec.status,
                deleted_at=rec.deleted_at,
                updated_at=rec.updated_at or utcnow(),
            )
        )
        if result.rowcount != 1:
            exists = self._s.get(ProviderConnectionRow, rec.connection_id)
            if exists is None:
                raise KeyError(rec.connection_id)
            raise VersionConflict
        self._s.flush()

    def audit(
        self,
        *,
        seller_id: uuid.UUID,
        connection_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._s.add(
            ProviderConnectionAuditRow(
                id=uuid.uuid4(),
                seller_account_id=seller_id,
                connection_id=connection_id,
                event_type=event_type,
                request_id=request_id,
                payload=dict(payload or {}),
                created_at=utcnow(),
            )
        )
        self._s.flush()

    def save_health(self, rec: ConnectionRecord) -> None:
        row = self._s.get(ProviderConnectionRow, rec.connection_id)
        if row is None:
            raise KeyError(rec.connection_id)
        row.health_state = rec.health_state
        row.health_reason = rec.health_reason
        row.health_checked_at = rec.health_checked_at
        row.consecutive_successes = rec.consecutive_successes
        row.consecutive_failures = rec.consecutive_failures
        row.last_probe_at = rec.last_probe_at
        row.next_probe_at = rec.next_probe_at
        row.capability_version = rec.capability_version
        row.updated_at = rec.updated_at or utcnow()
        self._s.flush()

    def list_probe_due(self, now: datetime, limit: int) -> list[ConnectionRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderConnectionRow)
                .where(
                    ProviderConnectionRow.status == "active",
                    ProviderConnectionRow.deleted_at.is_(None),
                    or_(
                        ProviderConnectionRow.next_probe_at.is_(None),
                        ProviderConnectionRow.next_probe_at <= now,
                    ),
                )
                .order_by(ProviderConnectionRow.next_probe_at.nullsfirst())
                .limit(max(0, limit))
            )
        )
        return [_to_record(r) for r in rows]

    def save_snapshot(
        self,
        *,
        connection_id: uuid.UUID,
        version: int,
        capabilities: list[Mapping[str, Any]] | list[dict[str, Any]],
    ) -> None:
        self._s.add(
            ConnectionCapabilitySnapshotRow(
                id=uuid.uuid4(),
                connection_id=connection_id,
                version=version,
                capabilities=[dict(c) for c in capabilities],
                created_at=utcnow(),
            )
        )
        self._s.flush()

    def list_snapshots(self, connection_id: uuid.UUID) -> list[CapabilitySnapshot]:
        rows = list(
            self._s.scalars(
                select(ConnectionCapabilitySnapshotRow)
                .where(ConnectionCapabilitySnapshotRow.connection_id == connection_id)
                .order_by(ConnectionCapabilitySnapshotRow.version)
            )
        )
        return [
            CapabilitySnapshot(
                connection_id=r.connection_id,
                version=r.version,
                capabilities=list(r.capabilities or []),
                created_at=r.created_at,
            )
            for r in rows
        ]

    def max_snapshot_version(self, connection_id: uuid.UUID) -> int:
        val = self._s.scalar(
            select(func.max(ConnectionCapabilitySnapshotRow.version)).where(
                ConnectionCapabilitySnapshotRow.connection_id == connection_id
            )
        )
        return int(val or 0)

    def save_lifecycle(self, rec: ConnectionRecord, expected_state: str) -> None:
        result = self._s.execute(
            update(ProviderConnectionRow)
            .where(
                ProviderConnectionRow.id == rec.connection_id,
                ProviderConnectionRow.lifecycle_state == expected_state,
            )
            .values(
                lifecycle_state=rec.lifecycle_state,
                supply_mode=rec.supply_mode,
                updated_at=rec.updated_at or utcnow(),
            )
        )
        if result.rowcount != 1:
            exists = self._s.get(ProviderConnectionRow, rec.connection_id)
            if exists is None:
                raise KeyError(rec.connection_id)
            raise VersionConflict
        self._s.flush()

    def list_all_active(self) -> list[ConnectionRecord]:
        rows = list(
            self._s.scalars(
                select(ProviderConnectionRow).where(
                    ProviderConnectionRow.status == "active",
                    ProviderConnectionRow.deleted_at.is_(None),
                )
            )
        )
        return [_to_record(r) for r in rows]


class SessionedConnectionStore:
    def __init__(self, maker: sessionmaker[Session]) -> None:
        self._maker = maker

    def _run(self, fn: Callable[[SQLConnectionStore], T]) -> T:
        session = self._maker()
        try:
            out = fn(SQLConnectionStore(session))
            session.commit()
            return out
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create(self, rec: ConnectionRecord) -> None:
        self._run(lambda s: s.create(rec))

    def get(self, connection_id: uuid.UUID) -> ConnectionRecord | None:
        return self._run(lambda s: s.get(connection_id))

    def list_by_seller(self, seller_id: uuid.UUID) -> list[ConnectionRecord]:
        return self._run(lambda s: s.list_by_seller(seller_id))

    def save_replace(self, rec: ConnectionRecord, expected_version: int) -> None:
        self._run(lambda s: s.save_replace(rec, expected_version))

    def audit(
        self,
        *,
        seller_id: uuid.UUID,
        connection_id: uuid.UUID | None,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._run(
            lambda s: s.audit(
                seller_id=seller_id,
                connection_id=connection_id,
                event_type=event_type,
                request_id=request_id,
                payload=payload,
            )
        )

    def save_health(self, rec: ConnectionRecord) -> None:
        self._run(lambda s: s.save_health(rec))

    def list_probe_due(self, now: datetime, limit: int) -> list[ConnectionRecord]:
        return self._run(lambda s: s.list_probe_due(now, limit))

    def save_snapshot(
        self,
        *,
        connection_id: uuid.UUID,
        version: int,
        capabilities: list[Mapping[str, Any]] | list[dict[str, Any]],
    ) -> None:
        self._run(
            lambda s: s.save_snapshot(
                connection_id=connection_id,
                version=version,
                capabilities=capabilities,
            )
        )

    def list_snapshots(self, connection_id: uuid.UUID) -> list[CapabilitySnapshot]:
        return self._run(lambda s: s.list_snapshots(connection_id))

    def max_snapshot_version(self, connection_id: uuid.UUID) -> int:
        return self._run(lambda s: s.max_snapshot_version(connection_id))

    def save_lifecycle(self, rec: ConnectionRecord, expected_state: str) -> None:
        self._run(lambda s: s.save_lifecycle(rec, expected_state))

    def list_all_active(self) -> list[ConnectionRecord]:
        return self._run(lambda s: s.list_all_active())
