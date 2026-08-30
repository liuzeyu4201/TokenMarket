"""SQLAlchemy models for phone-login authentication entities (SF04)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base
from app.domain.users.models import UserRole

__all__ = [
    "VerificationRequestIdempotencyRecord",
    "VerificationChallenge",
    "ProfileCompletionIntent",
    "AuthSession",
    "AuthenticationSecurityEvent",
]


class VerificationRequestIdempotencyRecord(Base):
    """Durable idempotency placeholder for request-verification-code."""

    __tablename__ = "verification_request_idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "state IN ('processing', 'succeeded', 'failed')",
            name="ck_vr_idempotency_state",
        ),
        CheckConstraint(
            "replay_until > created_at",
            name="ck_vr_idempotency_replay_until",
        ),
        CheckConstraint(
            "delete_after >= replay_until",
            name="ck_vr_idempotency_delete_after",
        ),
        CheckConstraint(
            "("
            "state = 'processing' AND http_status IS NULL "
            "AND result_code IS NULL AND completed_at IS NULL"
            ") OR ("
            "state IN ('succeeded', 'failed') AND http_status IS NOT NULL "
            "AND result_code IS NOT NULL AND completed_at IS NOT NULL"
            ")",
            name="ck_vr_idempotency_terminal_consistency",
        ),
        Index(
            "uq_vr_idempotency_operation_key",
            "operation",
            "key_version",
            "key_digest",
            unique=True,
        ),
        Index("idx_vr_idempotency_delete_after", "delete_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation: Mapped[str] = mapped_column(
        String(32), nullable=False, default="request_verification_code"
    )
    key_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phone_ref: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replay_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class VerificationChallenge(Base):
    """OTP challenge; user_id NULL means enumeration decoy."""

    __tablename__ = "verification_challenges"
    __table_args__ = (
        CheckConstraint(
            "state IN ("
            "'pending_delivery', 'dispatching', 'delivered', 'consumed', "
            "'locked', 'delivery_failed', 'superseded', 'expired'"
            ")",
            name="ck_vc_state",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 5",
            name="ck_vc_attempt_count",
        ),
        CheckConstraint("expires_at > created_at", name="ck_vc_expires_at"),
        CheckConstraint(
            "delete_after >= expires_at",
            name="ck_vc_delete_after",
        ),
        CheckConstraint(
            "send_started_at IS NULL OR state IN ("
            "'dispatching', 'delivered', 'delivery_failed'"
            ")",
            name="ck_vc_send_started_state",
        ),
        CheckConstraint(
            "state NOT IN ('delivered', 'delivery_failed') "
            "OR dispatch_finished_at IS NOT NULL",
            name="ck_vc_dispatch_finished_required",
        ),
        CheckConstraint(
            "state <> 'delivered' OR delivered_at IS NOT NULL",
            name="ck_vc_delivered_at",
        ),
        CheckConstraint(
            "state <> 'consumed' OR consumed_at IS NOT NULL",
            name="ck_vc_consumed_at",
        ),
        Index(
            "uq_vc_phone_ref_current",
            "phone_ref",
            unique=True,
            postgresql_where=text("state IN ('pending_delivery', 'delivered')"),
        ),
        Index("idx_vc_phone_ref_created_at", "phone_ref", "created_at"),
        Index(
            "idx_vc_pending_dispatch_claim",
            "state",
            "dispatch_lease_until",
            "created_at",
            postgresql_where=text("state = 'pending_delivery'"),
        ),
        Index(
            "idx_vc_dispatching_recovery",
            "state",
            "send_started_at",
            postgresql_where=text("state = 'dispatching'"),
        ),
        Index("idx_vc_user_id_created_at", "user_id", "created_at"),
        Index("idx_vc_delete_after", "delete_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    idempotency_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_request_idempotency_records.id"),
        nullable=False,
        unique=True,
    )
    phone_ref: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    phone_normalized: Mapped[str | None] = mapped_column(String(11), nullable=True)
    code_digest: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    code_salt: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    code_key_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    provider_request_ref: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    dispatch_lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatch_lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    send_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatch_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending_delivery"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProfileCompletionIntent(Base):
    """短时补全凭证；用户行仅在 consumed 事务中创建。"""

    __tablename__ = "profile_completion_intents"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_pci_expires_at"),
        Index("uq_pci_token_digest", "token_digest", unique=True),
        Index(
            "uq_pci_open_phone",
            "phone_normalized",
            unique=True,
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_normalized: Mapped[str] = mapped_column(String(11), nullable=False)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verification_challenges.id"), nullable=False
    )
    token_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    token_key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )


class AuthSession(Base):
    """Verified browser login session; raw token never stored."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > issued_at", name="ck_as_expires_at"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_as_revoked_at",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_as_revocation_consistency",
        ),
        CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN ("
            "'logout', 'superseded', 'account_disabled', 'expired_cleanup'"
            ")",
            name="ck_as_revocation_reason",
        ),
        Index(
            "uq_as_token_digest",
            "token_key_version",
            "token_digest",
            unique=True,
        ),
        Index(
            "uq_as_user_active",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("idx_as_user_issued_at", "user_id", "issued_at"),
        Index("idx_as_expires_at", "expires_at"),
        Index("idx_as_delete_after", "delete_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_digest: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    token_key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    role_snapshot: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AuthenticationSecurityEvent(Base):
    """Append-only authentication security audit record."""

    __tablename__ = "authentication_security_events"
    __table_args__ = (
        Index("idx_ase_event_type_occurred_at", "event_type", "occurred_at"),
        Index("idx_ase_delete_after", "delete_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_challenges.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_ref: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
