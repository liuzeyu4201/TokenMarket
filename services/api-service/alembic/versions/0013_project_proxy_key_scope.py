"""Project-scoped proxy key limits.

Revision ID: 0013_project_proxy_key_scope
Revises: 0012_provider_bindings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_project_proxy_key_scope"
down_revision: Union[str, None] = "0012_provider_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proxy_keys",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_proxy_keys_project",
        "proxy_keys",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "proxy_keys",
        sa.Column(
            "masked_prefix",
            sa.String(8),
            nullable=False,
            server_default="tmk-",
        ),
    )
    op.add_column(
        "proxy_keys",
        sa.Column(
            "protocols",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "proxy_keys",
        sa.Column(
            "allowed_models",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "proxy_keys",
        sa.Column(
            "allowed_cidrs",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("proxy_keys", sa.Column("quota_period", sa.String(8), nullable=True))
    op.add_column("proxy_keys", sa.Column("quota_limit", sa.Integer(), nullable=True))
    op.add_column(
        "proxy_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proxy_keys",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proxy_keys",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_proxy_keys_project", "proxy_keys", ["project_id"])
    op.create_table(
        "proxy_key_quota",
        sa.Column("key_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("accepted", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("proxy_key_quota")
    op.drop_index("ix_proxy_keys_project", table_name="proxy_keys")
    op.drop_column("proxy_keys", "rotated_at")
    op.drop_column("proxy_keys", "disabled_at")
    op.drop_column("proxy_keys", "expires_at")
    op.drop_column("proxy_keys", "quota_limit")
    op.drop_column("proxy_keys", "quota_period")
    op.drop_column("proxy_keys", "allowed_cidrs")
    op.drop_column("proxy_keys", "allowed_models")
    op.drop_column("proxy_keys", "protocols")
    op.drop_column("proxy_keys", "masked_prefix")
    op.drop_constraint("fk_proxy_keys_project", "proxy_keys", type_="foreignkey")
    op.drop_column("proxy_keys", "project_id")
