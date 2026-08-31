"""Project budget soft/hard thresholds (test quota, not a purchase product).

Revision ID: 0019_project_budgets
Revises: 0018_dedicated_replace
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0019_project_budgets"
down_revision: Union[str, None] = "0018_dedicated_replace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_budgets",
        sa.Column("project_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key_id", sa.String(64), primary_key=True, server_default=""),
        sa.Column("hard_minor", sa.BigInteger(), nullable=False),
        sa.Column("soft_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("hard_minor >= 0", name="ck_budget_hard"),
        sa.CheckConstraint("soft_minor >= 0", name="ck_budget_soft"),
        sa.CheckConstraint("soft_minor <= hard_minor", name="ck_budget_soft_le_hard"),
    )


def downgrade() -> None:
    op.drop_table("project_budgets")
