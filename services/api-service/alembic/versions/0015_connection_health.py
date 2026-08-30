"""Connection health and capability snapshots.

Revision ID: 0015_connection_health
Revises: 0014_provider_connections
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_connection_health"
down_revision: Union[str, None] = "0014_provider_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column(
            "health_state", sa.String(16), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "provider_connections",
        sa.Column("health_reason", sa.String(64), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "consecutive_successes", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "provider_connections",
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("next_probe_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "capability_version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        "ck_pc_health_state",
        "provider_connections",
        "health_state IN ('unknown', 'healthy', 'degraded', 'unhealthy')",
    )
    op.create_table(
        "connection_capability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_ccs_connection",
        "connection_capability_snapshots",
        ["connection_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ccs_connection", table_name="connection_capability_snapshots")
    op.drop_table("connection_capability_snapshots")
    op.drop_constraint("ck_pc_health_state", "provider_connections", type_="check")
    op.drop_column("provider_connections", "capability_version")
    op.drop_column("provider_connections", "next_probe_at")
    op.drop_column("provider_connections", "last_probe_at")
    op.drop_column("provider_connections", "consecutive_failures")
    op.drop_column("provider_connections", "consecutive_successes")
    op.drop_column("provider_connections", "health_checked_at")
    op.drop_column("provider_connections", "health_reason")
    op.drop_column("provider_connections", "health_state")
