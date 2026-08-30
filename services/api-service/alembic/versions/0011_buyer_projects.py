"""Buyer Project lifecycle tables.

Revision ID: 0011_buyer_projects
Revises: 0010_session_workspace
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_buyer_projects"
down_revision: Union[str, None] = "0010_session_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("name_normalized", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('shared', 'dedicated')",
            name="ck_projects_mode",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'suspended', 'archived')",
            name="ck_projects_status",
        ),
    )
    op.create_index(
        "uq_projects_owner_name_live",
        "projects",
        ["owner_account_id", "name_normalized"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_projects_owner", "projects", ["owner_account_id"])
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_project_mode_change()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              IF NEW.mode IS DISTINCT FROM OLD.mode THEN
                RAISE EXCEPTION 'project mode is immutable'
                  USING ERRCODE = '23000';
              END IF;
              RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_projects_mode_immutable
            BEFORE UPDATE ON projects
            FOR EACH ROW
            EXECUTE PROCEDURE reject_project_mode_change();
            """
        )
    )
    op.create_table(
        "project_protocols",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protocol", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "protocol"),
        sa.CheckConstraint(
            "protocol IN ('openai', 'anthropic', 'vertex')",
            name="ck_project_protocols_protocol",
        ),
    )
    op.create_table(
        "project_runtime_blockers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('key', 'in_flight_task', 'unsettled_ledger')",
            name="ck_project_runtime_blockers_kind",
        ),
    )
    op.create_index(
        "ix_project_blockers_open",
        "project_runtime_blockers",
        ["project_id"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "project_idempotency",
        sa.Column(
            "owner_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint(
            "owner_account_id",
            "idempotency_key",
            name="pk_project_idempotency",
        ),
    )
    op.create_table(
        "project_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.drop_table("project_audit_events")
    op.drop_table("project_idempotency")
    op.drop_index("ix_project_blockers_open", table_name="project_runtime_blockers")
    op.drop_table("project_runtime_blockers")
    op.drop_table("project_protocols")
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_projects_mode_immutable ON projects"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_project_mode_change()"))
    op.drop_index("ix_projects_owner", table_name="projects")
    op.drop_index("uq_projects_owner_name_live", table_name="projects")
    op.drop_table("projects")
