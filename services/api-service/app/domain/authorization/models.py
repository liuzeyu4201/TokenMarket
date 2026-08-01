"""SQLAlchemy models for authorization ownership and audit."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base

__all__ = [
    "ResourceOwnership",
    "AuthorizationSecurityEvent",
    "AuthorizationAuditOutbox",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResourceOwnership(Base):
    """Lightweight ownership fact for proxy_key / seller_key resources."""

    __tablename__ = "resource_ownerships"
    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", name="uq_resource_ownerships_type_id"
        ),
        Index(
            "idx_resource_ownerships_owner_type_status",
            "owner_user_id",
            "resource_type",
            "lifecycle_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    delete_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthorizationSecurityEvent(Base):
    """Append-only authorization security audit record."""

    __tablename__ = "authorization_security_events"
    __table_args__ = (
        Index("idx_ase_authz_request_id", "request_id"),
        Index("idx_ase_authz_event_type_occurred", "event_type", "occurred_at"),
        Index("idx_ase_authz_delete_after", "delete_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AuthorizationAuditOutbox(Base):
    """At-least-once delivery intent for authorization audit events."""

    __tablename__ = "authorization_audit_outbox"
    __table_args__ = (
        Index("idx_aao_state_available", "state", "available_at"),
        Index("idx_aao_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    published_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("NOW()"),
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
