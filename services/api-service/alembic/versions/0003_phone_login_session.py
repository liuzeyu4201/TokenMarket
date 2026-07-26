"""Create phone-login authentication tables (challenges, sessions, audit).

Revision ID: 0003_phone_login_session
Revises: 0002_users_registration

Additive only. Destructive downgrade drops events → sessions → challenges →
idempotency in reverse FK order. Does not edit 0001/0002.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_phone_login_session"
down_revision: Union[str, None] = "0002_users_registration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. verification_request_idempotency_records
    op.create_table(
        "verification_request_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("key_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False),
        sa.Column("phone_ref", postgresql.BYTEA(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("result_code", sa.String(length=64), nullable=True),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('processing', 'succeeded', 'failed')",
            name="ck_vr_idempotency_state",
        ),
        sa.CheckConstraint(
            "replay_until > created_at",
            name="ck_vr_idempotency_replay_until",
        ),
        sa.CheckConstraint(
            "delete_after >= replay_until",
            name="ck_vr_idempotency_delete_after",
        ),
        sa.CheckConstraint(
            "("
            "state = 'processing' AND http_status IS NULL "
            "AND result_code IS NULL AND completed_at IS NULL"
            ") OR ("
            "state IN ('succeeded', 'failed') AND http_status IS NOT NULL "
            "AND result_code IS NOT NULL AND completed_at IS NOT NULL"
            ")",
            name="ck_vr_idempotency_terminal_consistency",
        ),
        sa.UniqueConstraint(
            "operation",
            "key_version",
            "key_digest",
            name="uq_vr_idempotency_operation_key",
        ),
    )
    op.create_index(
        "idx_vr_idempotency_delete_after",
        "verification_request_idempotency_records",
        ["delete_after"],
    )

    # 2. verification_challenges
    op.create_table(
        "verification_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "idempotency_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("phone_ref", postgresql.BYTEA(), nullable=False),
        sa.Column("code_digest", postgresql.BYTEA(), nullable=True),
        sa.Column("code_salt", postgresql.BYTEA(), nullable=True),
        sa.Column("code_key_version", sa.SmallInteger(), nullable=True),
        sa.Column(
            "provider_request_ref",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("dispatch_lease_owner", sa.String(length=64), nullable=True),
        sa.Column("dispatch_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("send_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["idempotency_record_id"],
            ["verification_request_idempotency_records.id"],
        ),
        sa.UniqueConstraint(
            "idempotency_record_id",
            name="uq_vc_idempotency_record_id",
        ),
        sa.UniqueConstraint(
            "provider_request_ref",
            name="uq_vc_provider_request_ref",
        ),
        sa.CheckConstraint(
            "state IN ("
            "'pending_delivery', 'dispatching', 'delivered', 'consumed', "
            "'locked', 'delivery_failed', 'superseded', 'expired'"
            ")",
            name="ck_vc_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 5",
            name="ck_vc_attempt_count",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_vc_expires_at"),
        sa.CheckConstraint(
            "delete_after >= expires_at",
            name="ck_vc_delete_after",
        ),
        sa.CheckConstraint(
            "send_started_at IS NULL OR state IN ("
            "'dispatching', 'delivered', 'delivery_failed'"
            ")",
            name="ck_vc_send_started_state",
        ),
        sa.CheckConstraint(
            "state NOT IN ('delivered', 'delivery_failed') "
            "OR dispatch_finished_at IS NOT NULL",
            name="ck_vc_dispatch_finished_required",
        ),
        sa.CheckConstraint(
            "state <> 'delivered' OR delivered_at IS NOT NULL",
            name="ck_vc_delivered_at",
        ),
        sa.CheckConstraint(
            "state <> 'consumed' OR consumed_at IS NOT NULL",
            name="ck_vc_consumed_at",
        ),
    )
    op.create_index(
        "uq_vc_phone_ref_current",
        "verification_challenges",
        ["phone_ref"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending_delivery', 'delivered')"),
    )
    op.create_index(
        "idx_vc_phone_ref_created_at",
        "verification_challenges",
        ["phone_ref", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_vc_pending_dispatch_claim",
        "verification_challenges",
        ["state", "dispatch_lease_until", "created_at"],
        postgresql_where=sa.text("state = 'pending_delivery'"),
    )
    op.create_index(
        "idx_vc_dispatching_recovery",
        "verification_challenges",
        ["state", "send_started_at"],
        postgresql_where=sa.text("state = 'dispatching'"),
    )
    op.create_index(
        "idx_vc_user_id_created_at",
        "verification_challenges",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_vc_delete_after",
        "verification_challenges",
        ["delete_after"],
    )

    # 3. auth_sessions
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("token_key_version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "role_snapshot",
            postgresql.ENUM(
                "buyer", "seller", "both", name="user_role", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=24), nullable=True),
        sa.Column("created_request_id", sa.String(length=128), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "token_key_version",
            "token_digest",
            name="uq_as_token_digest",
        ),
        sa.CheckConstraint("expires_at > issued_at", name="ck_as_expires_at"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_as_revoked_at",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_as_revocation_consistency",
        ),
        sa.CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN ("
            "'logout', 'superseded', 'account_disabled', 'expired_cleanup'"
            ")",
            name="ck_as_revocation_reason",
        ),
    )
    op.create_index(
        "uq_as_user_active",
        "auth_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "idx_as_user_issued_at",
        "auth_sessions",
        ["user_id", sa.text("issued_at DESC")],
    )
    op.create_index("idx_as_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("idx_as_delete_after", "auth_sessions", ["delete_after"])

    # 4. authentication_security_events
    op.create_table(
        "authentication_security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("challenge_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_ref", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "safe_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["verification_challenges.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "idx_ase_event_type_occurred_at",
        "authentication_security_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "idx_ase_delete_after",
        "authentication_security_events",
        ["delete_after"],
    )


def downgrade() -> None:
    # Reverse FK order: events → sessions → challenges → idempotency
    op.drop_index(
        "idx_ase_delete_after",
        table_name="authentication_security_events",
    )
    op.drop_index(
        "idx_ase_event_type_occurred_at",
        table_name="authentication_security_events",
    )
    op.drop_table("authentication_security_events")

    op.drop_index("idx_as_delete_after", table_name="auth_sessions")
    op.drop_index("idx_as_expires_at", table_name="auth_sessions")
    op.drop_index("idx_as_user_issued_at", table_name="auth_sessions")
    op.drop_index("uq_as_user_active", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("idx_vc_delete_after", table_name="verification_challenges")
    op.drop_index("idx_vc_user_id_created_at", table_name="verification_challenges")
    op.drop_index(
        "idx_vc_dispatching_recovery", table_name="verification_challenges"
    )
    op.drop_index(
        "idx_vc_pending_dispatch_claim", table_name="verification_challenges"
    )
    op.drop_index("idx_vc_phone_ref_created_at", table_name="verification_challenges")
    op.drop_index("uq_vc_phone_ref_current", table_name="verification_challenges")
    op.drop_table("verification_challenges")

    op.drop_index(
        "idx_vr_idempotency_delete_after",
        table_name="verification_request_idempotency_records",
    )
    op.drop_table("verification_request_idempotency_records")
