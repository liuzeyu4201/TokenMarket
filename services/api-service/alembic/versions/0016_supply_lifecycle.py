"""Supply-mode lifecycle for Provider Connections.

Revision ID: 0016_supply_lifecycle
Revises: 0015_connection_health
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_supply_lifecycle"
down_revision: Union[str, None] = "0015_connection_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column(
            "lifecycle_state",
            sa.String(16),
            nullable=False,
            server_default="draft",
        ),
    )
    op.create_check_constraint(
        "ck_pc_lifecycle_state",
        "provider_connections",
        "lifecycle_state IN "
        "('draft', 'verified', 'listed', 'bound', 'paused', 'draining', 'retired')",
    )
    op.create_index(
        "uq_bindings_dedicated_connection",
        "provider_bindings",
        ["connection_id"],
        unique=True,
        postgresql_where=sa.text(
            "connection_id IS NOT NULL AND supply_mode = 'dedicated' "
            "AND status IN ('active', 'degraded')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_bindings_dedicated_connection", table_name="provider_bindings"
    )
    op.drop_constraint(
        "ck_pc_lifecycle_state", "provider_connections", type_="check"
    )
    op.drop_column("provider_connections", "lifecycle_state")
