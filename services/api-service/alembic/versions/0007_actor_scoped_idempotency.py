"""Scope seller/proxy key idempotency uniqueness to the acting principal.

Revision ID: 0007_actor_scoped_idempotency
Revises: 0006_proxy_keys_and_usage
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_actor_scoped_idempotency"
down_revision: Union[str, None] = "0006_proxy_keys_and_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "seller_key_idempotency_pkey", "seller_key_idempotency", type_="primary"
    )
    op.create_primary_key(
        "pk_seller_key_idempotency",
        "seller_key_idempotency",
        ["seller_id", "idempotency_key"],
    )
    op.drop_constraint(
        "proxy_key_idempotency_pkey", "proxy_key_idempotency", type_="primary"
    )
    op.create_primary_key(
        "pk_proxy_key_idempotency",
        "proxy_key_idempotency",
        ["buyer_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "pk_proxy_key_idempotency", "proxy_key_idempotency", type_="primary"
    )
    op.create_primary_key(
        "proxy_key_idempotency_pkey", "proxy_key_idempotency", ["idempotency_key"]
    )
    op.drop_constraint(
        "pk_seller_key_idempotency", "seller_key_idempotency", type_="primary"
    )
    op.create_primary_key(
        "seller_key_idempotency_pkey", "seller_key_idempotency", ["idempotency_key"]
    )
