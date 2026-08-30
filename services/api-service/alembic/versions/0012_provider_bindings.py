"""Provider Binding versions.

Revision ID: 0012_provider_bindings
Revises: 0011_buyer_projects
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_provider_bindings"
down_revision: Union[str, None] = "0011_buyer_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=False),
        sa.Column("supply_mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "allowed_providers",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "allowed_models",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "allowed_regions",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "protocol IN ('openai', 'anthropic', 'vertex')",
            name="ck_bindings_protocol",
        ),
        sa.CheckConstraint(
            "supply_mode IN ('shared', 'dedicated')",
            name="ck_bindings_supply_mode",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'validated', 'active', 'inactive', 'degraded')",
            name="ck_bindings_status",
        ),
    )
    op.create_index(
        "uq_bindings_active_protocol",
        "provider_bindings",
        ["project_id", "protocol"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_bindings_project",
        "provider_bindings",
        ["project_id"],
    )
    op.create_table(
        "provider_binding_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_binding_audit")
    op.drop_index("ix_bindings_project", table_name="provider_bindings")
    op.drop_index("uq_bindings_active_protocol", table_name="provider_bindings")
    op.drop_table("provider_bindings")
