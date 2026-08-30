"""Account session generation for single-session hardening.

Revision ID: 0009_session_generation
Revises: 0008_unified_phone_auth

Expand-only. Adds session_generation on users and auth_sessions plus
client_hint on auth_sessions. Downgrade drops the columns.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_session_generation"
down_revision: Union[str, None] = "0008_unified_phone_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "session_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "auth_sessions",
        sa.Column(
            "session_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("client_hint", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "client_hint")
    op.drop_column("auth_sessions", "session_generation")
    op.drop_column("users", "session_generation")
