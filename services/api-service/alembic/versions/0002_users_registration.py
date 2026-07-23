"""Create users and registration_idempotency_records tables.

Revision ID: 0002_users_registration
Revises: 0001_baseline
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_users_registration"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role = postgresql.ENUM(
        "buyer", "seller", "both", name="user_role", create_type=False
    )
    user_status = postgresql.ENUM(
        "active", "suspended", name="user_status", create_type=False
    )
    user_role.create(op.get_bind(), checkfirst=True)
    user_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("phone_normalized", sa.String(length=11), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("buyer", "seller", "both", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("active", "suspended", name="user_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
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
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("phone_normalized", name="uq_users_phone_normalized"),
        sa.CheckConstraint(
            "phone_normalized ~ '^[1][3-9][0-9]{9}$'",
            name="ck_users_phone_normalized",
        ),
    )
    op.create_index("idx_users_created_at", "users", ["created_at"])

    op.create_table(
        "registration_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_code", sa.String(length=64), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_reg_idempotency_key"),
    )
    op.create_index(
        "idx_reg_idempotency_expires_at",
        "registration_idempotency_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_reg_idempotency_expires_at", table_name="registration_idempotency_records"
    )
    op.drop_table("registration_idempotency_records")
    op.drop_index("idx_users_created_at", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_status")
    op.execute("DROP TYPE IF EXISTS user_role")
