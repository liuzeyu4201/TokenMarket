"""Versioned rate cards, seller quotes, and request price locks.

Revision ID: 0002_pricing_versions
Revises: 0001_baseline
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_pricing_versions"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_rate_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("scale", sa.SmallInteger(), nullable=False, server_default="6"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("buyer_multiplier_bps", sa.Integer(), nullable=False),
        sa.Column("seller_quote_min_bps", sa.Integer(), nullable=False),
        sa.Column("seller_quote_max_bps", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','previewed','approved','published','superseded')",
            name="ck_pricing_status",
        ),
        sa.CheckConstraint(
            "buyer_multiplier_bps >= seller_quote_max_bps",
            name="ck_pricing_nonneg_spread",
        ),
        sa.CheckConstraint(
            "seller_quote_min_bps <= seller_quote_max_bps",
            name="ck_pricing_quote_bounds",
        ),
    )
    op.create_table(
        "pricing_rate_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("pricing_rate_versions.version_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=False, server_default=""),
        sa.Column("model", sa.String(128), nullable=False, server_default="*"),
        sa.Column("endpoint_id", sa.String(256), nullable=False, server_default="*"),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False, server_default="*"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("unit", sa.String(16), nullable=False, server_default="token"),
        sa.Column("rate_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.String(32), nullable=True),
        sa.Column("valid_to", sa.String(32), nullable=True),
        sa.CheckConstraint("rate_minor_units >= 0", name="ck_pricing_rate_nonneg"),
    )
    op.create_index(
        "ix_pricing_rows_lookup",
        "pricing_rate_rows",
        ["version_id", "provider", "dimension"],
    )
    op.create_table(
        "pricing_seller_quotes",
        sa.Column("seller_id", sa.String(64), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("pricing_rate_versions.version_id"),
            primary_key=True,
        ),
        sa.Column("multiplier_bps", sa.Integer(), nullable=False),
    )
    op.create_table(
        "pricing_locks",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("rate_version", sa.String(64), nullable=False),
        sa.Column("buyer_bps", sa.Integer(), nullable=False),
        sa.Column("seller_bps", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pricing_locks")
    op.drop_table("pricing_seller_quotes")
    op.drop_index("ix_pricing_rows_lookup", table_name="pricing_rate_rows")
    op.drop_table("pricing_rate_rows")
    op.drop_table("pricing_rate_versions")
