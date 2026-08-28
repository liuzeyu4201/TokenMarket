"""mode=test migrate must not follow a production-shaped ambient DSN."""

from __future__ import annotations

import pytest

from workflow.cli import WorkflowError, bind_test_migration_environment, dsn_is_production_shaped


def test_production_shaped_ambient_dsn_refused_before_alembic() -> None:
    env = {
        "DATABASE_URL": "postgresql://app:secret@prod.example.com:5432/tokenmarket",
        "PATH": "/usr/bin",
    }
    with pytest.raises(WorkflowError) as exc:
        bind_test_migration_environment(env)
    assert exc.value.code == "INVALID_TARGET"
    assert "before Alembic" in exc.value.message
    bound = bind_test_migration_environment(
        {
            "PATH": "/usr/bin",
            "TOKENMARKET_TEST_DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/tm",
        }
    )
    assert bound["DATABASE_URL"].startswith("postgresql://")
    assert "127.0.0.1" in bound["DATABASE_URL"]


def test_loopback_is_not_production_shaped() -> None:
    assert dsn_is_production_shaped("postgresql://u:p@127.0.0.1:5432/db") is False
    assert dsn_is_production_shaped("postgresql://u:p@db.internal:5432/db") is True
