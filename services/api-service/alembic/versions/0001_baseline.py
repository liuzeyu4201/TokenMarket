"""Baseline migration for api-service.

This revision initializes the Alembic graph without creating any business
schema. Business tables will be introduced by later features.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SF01 creates no business tables.
    pass


def downgrade() -> None:
    # SF01 creates no business tables.
    pass
