"""Alembic 0005/0006 seller keys, proxy keys, usage logs."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration


def test_seller_proxy_usage_tables_on_head(postgres_container: PostgresHandle) -> None:
    url = postgres_container.database_url()
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        for name in (
            "seller_api_keys",
            "seller_key_idempotency",
            "proxy_keys",
            "proxy_key_idempotency",
            "usage_logs",
            "usage_conflicts",
        ):
            assert name in tables, name
    finally:
        engine.dispose()
    down = run_alembic(url, "downgrade", "0004_role_access_isolation")
    assert down.returncode == 0, down.stdout + down.stderr
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "seller_api_keys" not in tables
        assert "proxy_keys" not in tables
        assert "usage_logs" not in tables
    finally:
        engine.dispose()
