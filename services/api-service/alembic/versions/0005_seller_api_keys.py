"""Seller API keys (SF08/SF09).

Revision ID: 0005_seller_api_keys
Revises: 0004_role_access_isolation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_seller_api_keys"
down_revision: Union[str, None] = "0004_role_access_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("masked_hint", sa.String(32), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("tag", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("remaining_quota", sa.String(64), nullable=True),
        sa.Column("quota_unit", sa.String(32), nullable=True),
        sa.Column(
            "administrative_state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "health_state",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("created_request_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "soft_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.UniqueConstraint("platform", "fingerprint", name="uq_seller_api_keys_fp"),
    )
    op.create_table(
        "seller_key_idempotency",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("seller_key_idempotency")
    op.drop_table("seller_api_keys")
