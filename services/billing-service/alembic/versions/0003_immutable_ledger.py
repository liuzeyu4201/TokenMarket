"""Immutable ledger entries and reservations.

Revision ID: 0003_immutable_ledger
Revises: 0002_pricing_versions
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_immutable_ledger"
down_revision: Union[str, None] = "0002_pricing_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("entry_id", sa.String(64), primary_key=True),
        sa.Column("journal_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=False),
        sa.Column("account_kind", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("key_id", sa.String(64), nullable=True),
        sa.Column("amount_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default="test_quota"),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rate_version", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("reverses_entry_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor_units >= 0", name="ck_ledger_amount_nonneg"),
        sa.CheckConstraint(
            "direction IN ('debit','credit')", name="ck_ledger_direction"
        ),
        sa.CheckConstraint(
            "status IN ('reserved','settled','released','unresolved','reversed')",
            name="ck_ledger_status",
        ),
        sa.CheckConstraint(
            "account_kind IN ('buyer_quota','project_quota','key_quota',"
            "'seller_earning','platform_spread')",
            name="ck_ledger_kind",
        ),
    )
    op.create_index("ix_ledger_entries_account", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_request", "ledger_entries", ["request_id"])
    op.execute(
        """
        CREATE FUNCTION ledger_entries_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'ledger entries are append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_no_mutate
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledger_entries_immutable();
        """
    )
    op.create_table(
        "ledger_reservations",
        sa.Column("reservation_id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("remaining_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rate_version", sa.String(64), nullable=False),
        sa.Column("journal_id", sa.String(64), nullable=False),
        sa.Column("unresolved_reason", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_ledger_res_request"),
        sa.UniqueConstraint("idempotency_key", name="uq_ledger_res_idempotency"),
        sa.CheckConstraint("amount_minor > 0", name="ck_ledger_res_amount"),
        sa.CheckConstraint(
            "status IN ('held','consumed','released','unresolved')",
            name="ck_ledger_res_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("ledger_reservations")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_no_mutate ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS ledger_entries_immutable();")
    op.drop_index("ix_ledger_entries_request", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_account", table_name="ledger_entries")
    op.drop_table("ledger_entries")
