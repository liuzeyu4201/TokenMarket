"""Dedicated binding replace: draining_connection_id.

Revision ID: 0018_dedicated_replace
Revises: 0017_seller_workbench
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0018_dedicated_replace"
down_revision: Union[str, None] = "0017_seller_workbench"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_bindings",
        sa.Column("draining_connection_id", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_bindings", "draining_connection_id")
