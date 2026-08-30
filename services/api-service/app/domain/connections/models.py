"""Connection records and ORM."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CapabilitySnapshot:
    connection_id: uuid.UUID
    version: int
    capabilities: list[dict[str, Any]]
    created_at: datetime


@dataclass
class ConnectionRecord:
    connection_id: uuid.UUID
    seller_account_id: uuid.UUID
    provider: str
    supply_mode: str
    auth_type: str
    base_url: str
    region: str | None
    purpose: str | None
    project_number: str | None
    location: str | None
    nonce: bytes | None
    ciphertext: bytes | None
    tag: bytes | None
    key_version: str | None
    credential_fingerprint: str
    credential_version: int
    status: str
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    health_state: str = "unknown"
    health_reason: str | None = None
    health_checked_at: datetime | None = None
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    last_probe_at: datetime | None = None
    next_probe_at: datetime | None = None
    capability_version: int = 0
    lifecycle_state: str = "draft"

    def usable(self) -> bool:
        return (
            self.status == "active"
            and self.deleted_at is None
            and self.ciphertext is not None
            and self.nonce is not None
            and self.tag is not None
        )

    def to_public(self) -> dict[str, Any]:
        """Safe metadata only — never ciphertext, nonce, tag, or plaintext."""
        return {
            "connection_id": str(self.connection_id),
            "seller_account_id": str(self.seller_account_id),
            "provider": self.provider,
            "supply_mode": self.supply_mode,
            "auth_type": self.auth_type,
            "base_url": self.base_url,
            "region": self.region,
            "purpose": self.purpose,
            "project_number": self.project_number,
            "location": self.location,
            "credential_fingerprint": self.credential_fingerprint,
            "credential_version": self.credential_version,
            "status": self.status,
            "health_state": self.health_state,
            "health_reason": self.health_reason,
            "capability_version": self.capability_version,
            "lifecycle_state": self.lifecycle_state,
        }


class ProviderConnectionRow(Base):
    __tablename__ = "provider_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    supply_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credential_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    health_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )
    health_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_successes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_probe_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_probe_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    capability_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifecycle_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )


class ConnectionCapabilitySnapshotRow(Base):
    __tablename__ = "connection_capability_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    capabilities: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ProviderConnectionAuditRow(Base):
    __tablename__ = "provider_connection_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
