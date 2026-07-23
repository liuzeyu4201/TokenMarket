"""Alembic upgrade/downgrade for users registration tables (T067)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration


def test_users_migration_upgrade_and_downgrade(
    postgres_container: PostgresHandle,
) -> None:
    url = postgres_container.database_url()
    up = run_alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr

    engine = create_engine(url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert "users" in tables
        assert "registration_idempotency_records" in tables
        with engine.connect() as conn:
            cols = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'users'"
                    )
                )
            }
            assert "phone_normalized" in cols
            assert "nickname" in cols
            assert "role" in cols
    finally:
        engine.dispose()

    down = run_alembic(url, "downgrade", "0001_baseline")
    assert down.returncode == 0, down.stdout + down.stderr

    engine = create_engine(url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert "users" not in tables
        assert "registration_idempotency_records" not in tables
    finally:
        engine.dispose()
