"""Session workspace for buyer/seller lens.

Revision ID: 0010_session_workspace
Revises: 0009_session_generation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_session_workspace"
down_revision: Union[str, None] = "0009_session_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column(
            "workspace",
            sa.String(length=8),
            nullable=False,
            server_default="buyer",
        ),
    )
    op.create_check_constraint(
        "ck_as_workspace",
        "auth_sessions",
        "workspace IN ('buyer', 'seller')",
    )
    op.execute(
        sa.text(
            "UPDATE auth_sessions SET workspace = 'seller' "
            "WHERE role_snapshot = 'seller'"
        )
    )


def downgrade() -> None:
    op.drop_constraint("ck_as_workspace", "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "workspace")
