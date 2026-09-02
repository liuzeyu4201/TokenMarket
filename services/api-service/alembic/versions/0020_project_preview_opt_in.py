"""Project preview/beta opt-in flag (catalog admit).

Revision ID: 0020_project_preview_opt_in
Revises: 0019_project_budgets
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020_project_preview_opt_in"
down_revision: Union[str, None] = "0019_project_budgets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "preview_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "preview_opt_in")
