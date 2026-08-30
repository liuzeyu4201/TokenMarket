"""Provider Connection encrypted credentials.

Revision ID: 0014_provider_connections
Revises: 0013_project_proxy_key_scope
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_provider_connections"
down_revision: Union[str, None] = "0013_project_proxy_key_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "seller_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("supply_mode", sa.String(16), nullable=False),
        sa.Column("auth_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("purpose", sa.String(64), nullable=True),
        sa.Column("project_number", sa.String(64), nullable=True),
        sa.Column("location", sa.String(64), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("tag", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(32), nullable=True),
        sa.Column("credential_fingerprint", sa.String(64), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "provider IN ('openai', 'anthropic', 'vertex')",
            name="ck_pc_provider",
        ),
        sa.CheckConstraint(
            "supply_mode IN ('shared', 'dedicated')",
            name="ck_pc_supply_mode",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deleted')",
            name="ck_pc_status",
        ),
    )
    op.create_index("ix_pc_seller", "provider_connections", ["seller_account_id"])
    op.create_table(
        "provider_connection_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.drop_table("provider_connection_audit")
    op.drop_index("ix_pc_seller", table_name="provider_connections")
    op.drop_table("provider_connections")
