"""Create authorization ownership and audit tables (SF05).

Revision ID: 0004_role_access_isolation
Revises: 0003_phone_login_session

Additive only. Downgrade drops outbox → events → ownership.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_role_access_isolation"
down_revision: Union[str, None] = "0003_phone_login_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_ownerships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("created_request_id", sa.String(length=128), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "resource_type", "resource_id", name="uq_resource_ownerships_type_id"
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'disabled', 'soft_deleted')",
            name="ck_resource_ownerships_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_resource_ownerships_version"),
    )
    op.create_index(
        "idx_resource_ownerships_owner_type_status",
        "resource_ownerships",
        ["owner_user_id", "resource_type", "lifecycle_status"],
    )

    op.create_table(
        "authorization_security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
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
    )
    op.create_index(
        "idx_ase_authz_request_id",
        "authorization_security_events",
        ["request_id"],
    )
    op.create_index(
        "idx_ase_authz_event_type_occurred",
        "authorization_security_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "idx_ase_authz_delete_after",
        "authorization_security_events",
        ["delete_after"],
    )

    op.create_table(
        "authorization_audit_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("published_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'published', 'failed')",
            name="ck_authz_outbox_state",
        ),
    )
    op.create_index(
        "idx_aao_state_available",
        "authorization_audit_outbox",
        ["state", "available_at"],
    )
    op.create_index(
        "idx_aao_request_id",
        "authorization_audit_outbox",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_aao_request_id", table_name="authorization_audit_outbox")
    op.drop_index("idx_aao_state_available", table_name="authorization_audit_outbox")
    op.drop_table("authorization_audit_outbox")
    op.drop_index(
        "idx_ase_authz_delete_after", table_name="authorization_security_events"
    )
    op.drop_index(
        "idx_ase_authz_event_type_occurred",
        table_name="authorization_security_events",
    )
    op.drop_index("idx_ase_authz_request_id", table_name="authorization_security_events")
    op.drop_table("authorization_security_events")
    op.drop_index(
        "idx_resource_ownerships_owner_type_status",
        table_name="resource_ownerships",
    )
    op.drop_table("resource_ownerships")
