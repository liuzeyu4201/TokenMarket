"""Unified phone auth: registration-capable challenges and profile intents.

Revision ID: 0008_unified_phone_auth
Revises: 0007_actor_scoped_idempotency

Expand-only. Adds nullable phone_normalized on verification_challenges and
profile_completion_intents. Downgrade drops the table then the column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_unified_phone_auth"
down_revision: Union[str, None] = "0007_actor_scoped_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "verification_challenges",
        sa.Column("phone_normalized", sa.String(length=11), nullable=True),
    )
    op.create_table(
        "profile_completion_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("phone_normalized", sa.String(length=11), nullable=False),
        sa.Column("challenge_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_digest", postgresql.BYTEA(), nullable=False),
        sa.Column("token_key_version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["challenge_id"], ["verification_challenges.id"]),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_pci_expires_at",
        ),
        sa.UniqueConstraint("token_digest", name="uq_pci_token_digest"),
    )
    op.create_index(
        "uq_pci_open_phone",
        "profile_completion_intents",
        ["phone_normalized"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_pci_open_phone", table_name="profile_completion_intents")
    op.drop_table("profile_completion_intents")
    op.drop_column("verification_challenges", "phone_normalized")
