"""Seller quote workbench tables.

Revision ID: 0017_seller_workbench
Revises: 0016_supply_lifecycle
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0017_seller_workbench"
down_revision: Union[str, None] = "0016_supply_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_quote_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_id", UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("multiplier_bps", sa.Integer(), nullable=False),
        sa.Column("rate_version", sa.String(64), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("multiplier_bps >= 0", name="ck_seller_quote_bps_nonneg"),
        sa.UniqueConstraint("connection_id", "seq", name="uq_seller_quote_seq"),
    )
    op.create_table(
        "seller_declared_capacity",
        sa.Column("connection_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("declared_capacity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("declared_capacity >= 0", name="ck_seller_capacity_nonneg"),
    )
    op.create_table(
        "seller_workbench_audit",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_id", UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before_json", JSONB, nullable=True),
        sa.Column("after_json", JSONB, nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("seller_workbench_audit")
    op.drop_table("seller_declared_capacity")
    op.drop_table("seller_quote_revisions")
