"""Alembic 0010 → 0011 Project tables and mode trigger."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def test_projects_migration_forward_back(
    postgres_container: PostgresHandle,
) -> None:
    url = postgres_container.database_url()
    up = run_alembic(url, "upgrade", "0011_buyer_projects")
    assert up.returncode == 0, up.stdout + up.stderr
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        for name in (
            "projects",
            "project_protocols",
            "project_runtime_blockers",
            "project_idempotency",
            "project_audit_events",
        ):
            assert name in tables
        with engine.connect() as conn:
            rev = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert rev == "0011_buyer_projects"
            idx = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'projects' AND indexname = "
                    "'uq_projects_owner_name_live'"
                )
            ).scalar_one()
            assert idx == "uq_projects_owner_name_live"
    finally:
        engine.dispose()

    down = run_alembic(url, "downgrade", "0010_session_workspace")
    assert down.returncode == 0, down.stdout + down.stderr
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "projects" not in tables
        assert "users" in tables
        assert "auth_sessions" in tables
        with engine.connect() as conn:
            rev = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert rev == "0010_session_workspace"
    finally:
        engine.dispose()

    retry = run_alembic(url, "upgrade", "head")
    assert retry.returncode == 0, retry.stdout + retry.stderr
