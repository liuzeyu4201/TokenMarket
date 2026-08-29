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


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@127.0.0.1:5432/tm?host=prod.example.com",
        "postgresql://u:p@127.0.0.1:5432/tm?hostaddr=10.0.0.8",
        "postgresql://u:p@127.0.0.1:5432/tm?passfile=/etc/passwd",
        "postgresql://u:p@127.0.0.1:5432/tm?HOST=prod.example.com",
        "postgresql://u:p@127.0.0.1:5432/tm?PassFile=/tmp/pgpass",
        "postgresql://u:p@127.0.0.1:5432,10.0.0.8:5432/tm",
    ],
)
def test_loopback_authority_host_overrides_rejected(url: str) -> None:
    """tm-test-dsn-host-override."""
    env = {"PATH": "/usr/bin", "TOKENMARKET_TEST_DATABASE_URL": url}
    with pytest.raises(WorkflowError) as exc:
        bind_test_migration_environment(env)
    assert exc.value.code == "INVALID_TARGET"


def test_both_migration_owners_receive_attested_loopback_dsn() -> None:
    bound = bind_test_migration_environment(
        {
            "PATH": "/usr/bin",
            "TOKENMARKET_TEST_DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/tm?sslmode=disable",
        }
    )
    attested = bound["DATABASE_URL"]
    assert attested == bound["TOKENMARKET_TEST_DATABASE_URL"]
    assert attested == bound["TOKENMARKET_ATTESTED_TEST_DSN"]
    assert "127.0.0.1" in attested
    assert "sslmode" not in attested
    assert "?" not in attested
    api_env = dict(bound)
    billing_env = dict(bound)
    assert api_env["DATABASE_URL"] == billing_env["DATABASE_URL"] == attested
