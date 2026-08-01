"""Migration 0004_role_access_isolation upgrade/downgrade smoke."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration


def test_authorization_tables_present_after_head(
    auth_migrated_postgres: str,
) -> None:
    """auth_migrated_postgres is upgraded to head (includes 0004)."""
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert "resource_ownerships" in tables
        assert "authorization_security_events" in tables
        assert "authorization_audit_outbox" in tables
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM resource_ownerships LIMIT 0"))
    finally:
        engine.dispose()


def test_authorization_migration_downgrade_upgrade(
    auth_postgres_container: object,
) -> None:
    handle = auth_postgres_container
    url = handle.database_url()  # type: ignore[attr-defined]
    run_alembic(url, "upgrade", "head")
    run_alembic(url, "downgrade", "0003_phone_login_session")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "resource_ownerships" not in tables
    finally:
        engine.dispose()
    run_alembic(url, "upgrade", "head")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "resource_ownerships" in tables
    finally:
        engine.dispose()
