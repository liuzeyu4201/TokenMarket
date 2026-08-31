"""Unresolved cases, recon tickets, and evidence event ids.

Revision ID: 0004_recon_unresolved
Revises: 0003_immutable_ledger
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_recon_unresolved"
down_revision: Union[str, None] = "0003_immutable_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ledger_unresolved_cases",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("amount_exposure_minor", sa.BigInteger(), nullable=False),
        sa.Column("next_action", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("missing_evidence", sa.String(64), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_id", sa.String(64), nullable=True),
        sa.Column("rate_version", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_exposure_minor >= 0", name="ck_unresolved_exposure"),
        sa.CheckConstraint(
            "reason_code IN ("
            "'MISSING_AMOUNT','MISSING_USAGE','PARSE_FAILED','ASYNC_INCOMPLETE')",
            name="ck_unresolved_reason",
        ),
    )
    op.create_table(
        "ledger_recon_tickets",
        sa.Column("ticket_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("reported_minor", sa.BigInteger(), nullable=True),
        sa.Column("computed_minor", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('VARIANCE','ORPHAN','UNBALANCED')", name="ck_recon_kind"
        ),
    )
    op.create_table(
        "ledger_evidence_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ledger_recon_audit",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("preview_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ledger_recon_audit")
    op.drop_table("ledger_evidence_events")
    op.drop_table("ledger_recon_tickets")
    op.drop_table("ledger_unresolved_cases")
