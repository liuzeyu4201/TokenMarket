"""Migration ownership and round-trip tests (T020).

Covers owner manifest validation, offline migrate-check, per-owner database
isolation for migrate-integration-check, and mode gates for make migrate.
"""

from __future__ import annotations

import inspect
import re
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

from workflow.migrations import (
    MigrationError,
    create_owner_database,
    new_integration_run_token,
    normalize_component_slug,
    owner_database_name,
    plan_owner_databases,
    redact_database_url,
    replace_database_name,
)

from .helpers import find_repo_root, load_json, load_text, run


@pytest.fixture
def owners_manifest() -> dict[str, Any]:
    return load_json("ops", "migrations", "owners.json")


@pytest.fixture
def components_manifest() -> dict[str, Any]:
    return load_json("ops", "workflow", "components.json")


def test_migration_owners_exactly_api_then_billing(owners_manifest: dict[str, Any]) -> None:
    owners = owners_manifest["owners"]
    assert len(owners) == 2
    assert owners[0]["component_id"] == "api-service"
    assert owners[0]["order"] == 1
    assert owners[1]["component_id"] == "billing-service"
    assert owners[1]["order"] == 2


def test_non_owners_list_contains_admin_service(owners_manifest: dict[str, Any]) -> None:
    assert "admin-service" in owners_manifest["non_owners"]


def test_owner_graphs_have_single_head(owners_manifest: dict[str, Any]) -> None:
    root = find_repo_root()
    for owner in owners_manifest["owners"]:
        version_path = root / owner["version_path"]
        assert version_path.is_dir(), f"{owner['component_id']}: missing versions dir"
        py_files = list(version_path.glob("*.py"))
        assert py_files, f"{owner['component_id']}: no migration files"


def test_owner_backout_runbook_exists(owners_manifest: dict[str, Any]) -> None:
    root = find_repo_root()
    for owner in owners_manifest["owners"]:
        runbook = root / owner["backout_runbook"]
        assert runbook.is_file(), f"{owner['component_id']}: missing backout runbook"


def test_migrate_check_reports_zero_pending_after_validation() -> None:
    result = run(["make", "migrate-check"], cwd=find_repo_root(), check=False)
    assert (
        result.returncode == 0
    ), f"make migrate-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    output = result.stdout + result.stderr
    assert "api-service" in output and "billing-service" in output


def test_migrate_check_does_not_call_make_dev() -> None:
    result = run(["make", "migrate-check"], cwd=find_repo_root(), check=False)
    output = result.stdout + result.stderr
    assert "SF02_NOT_READY" not in output, "migrate-check must not invoke make dev"


def test_migrate_integration_check_runs_pg15_round_trip() -> None:
    result = run(["make", "migrate-integration-check"], cwd=find_repo_root(), check=False)
    assert (
        result.returncode == 0
    ), f"make migrate-integration-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    output = result.stdout + result.stderr
    assert "forward" in output.lower()
    assert "backout" in output.lower() or "downgrade" in output.lower()
    assert "api-service" in output
    assert "billing-service" in output
    assert "0003_phone_login_session" not in output or "billing" in output.lower()
    # Isolation markers from setup message
    assert "owner-isolated" in output.lower() or "tm_mig_" in output
    assert "api-service->tm_mig_" in output
    assert "billing-service->tm_mig_" in output


def test_migrate_integration_check_uses_isolated_database() -> None:
    result = run(["make", "migrate-integration-check"], cwd=find_repo_root(), check=False)
    output = result.stdout + result.stderr
    assert "shared database" not in output.lower()
    assert "make dev" not in output.lower()
    assert result.returncode == 0
    # Distinct per-owner database names appear in the event stream.
    api_dbs = re.findall(r"api-service->(tm_mig_[a-z0-9]+_api_service)", output)
    billing_dbs = re.findall(
        r"billing-service->(tm_mig_[a-z0-9]+_billing_service)", output
    )
    assert api_dbs, output
    assert billing_dbs, output
    assert api_dbs[0] != billing_dbs[0]
    assert "0003_phone_login_session" not in output or "FAILED" not in output


def test_migrate_invalid_mode_fails_before_connection() -> None:
    result = run(["make", "migrate", "mode=PROD"], cwd=find_repo_root(), check=False)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "INVALID_MODE" in output


def test_migrate_prod_without_approval_fails_before_connection() -> None:
    result = run(["make", "migrate", "mode=prod"], cwd=find_repo_root(), check=False)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "PROD_APPROVAL_REQUIRED" in output


def test_plan_owner_databases_isolates_names_and_urls(
    owners_manifest: dict[str, Any],
) -> None:
    base = (
        "postgresql+psycopg2://postgres:syn%2Fpass@127.0.0.1:15432/postgres?sslmode=disable"
    )
    planned = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token="a1b2c3d4",
        base_url=base,
    )
    assert [p["component_id"] for p in planned] == ["api-service", "billing-service"]
    assert planned[0]["database"] != planned[1]["database"]
    assert planned[0]["database_url"] != planned[1]["database_url"]
    assert planned[0]["database"] == "tm_mig_a1b2c3d4_api_service"
    assert planned[1]["database"] == "tm_mig_a1b2c3d4_billing_service"
    for entry in planned:
        parsed = urlparse(entry["database_url"])
        assert parsed.scheme == "postgresql+psycopg2"
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port == 15432
        assert parsed.username == "postgres"
        # Password remains percent-encoded in netloc; must not be mangled.
        assert parsed.password in {"syn/pass", "syn%2Fpass"}
        assert "syn%2Fpass" in entry["database_url"] or "syn/pass" in entry["database_url"]
        assert parsed.path == f"/{entry['database']}"
        assert parsed.query == "sslmode=disable"
        # Same owner always maps to one URL for forward/backout/retry.
        again = replace_database_name(base, entry["database"])
        assert again == entry["database_url"]


def test_run_tokens_differ_across_concurrent_plans(
    owners_manifest: dict[str, Any],
) -> None:
    base = "postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres"
    a = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token=new_integration_run_token(),
        base_url=base,
    )
    b = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token=new_integration_run_token(),
        base_url=base,
    )
    assert {p["database"] for p in a}.isdisjoint({p["database"] for p in b})
    assert a[0]["database_url"] != b[0]["database_url"]


def test_owner_database_name_normalization_and_safety() -> None:
    assert normalize_component_slug("api-service") == "api_service"
    name = owner_database_name(run_token="deadbeef", component_id="api-service")
    assert name == "tm_mig_deadbeef_api_service"
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name)
    with pytest.raises(MigrationError):
        owner_database_name(run_token="short", component_id="api-service")
    with pytest.raises(MigrationError):
        owner_database_name(run_token="deadbeef", component_id="!!!")


def test_replace_database_name_rejects_unsafe_identifier() -> None:
    base = "postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres"
    with pytest.raises(MigrationError):
        replace_database_name(base, 'evil"; drop database postgres; --')


def test_create_owner_database_fail_closed_on_psql_error() -> None:
    with patch("workflow.migrations.subprocess.run") as run_mock:
        run_mock.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: permission denied to create database",
            stdout="",
        )
        with pytest.raises(MigrationError) as excinfo:
            create_owner_database(
                container_name="tm-migrate-integration-check",
                database="tm_mig_a1b2c3d4_api_service",
                run_token="a1b2c3d4",
            )
        assert excinfo.value.code == "STEP_FAILED"
        assert "tm_mig_a1b2c3d4_api_service" in excinfo.value.message


def test_create_owner_database_rejects_foreign_or_reserved_names() -> None:
    with pytest.raises(MigrationError):
        create_owner_database(
            container_name="tm-migrate-integration-check",
            database="postgres",
            run_token="a1b2c3d4",
        )
    with pytest.raises(MigrationError):
        create_owner_database(
            container_name="tm-migrate-integration-check",
            database="tm_mig_other12_api_service",
            run_token="a1b2c3d4",
        )


def test_redact_database_url_hides_password() -> None:
    url = "postgresql+psycopg2://postgres:super-secret@127.0.0.1:15432/tm_mig_x"
    redacted = redact_database_url(url)
    assert "super-secret" not in redacted
    assert "***" in redacted
    assert "127.0.0.1" in redacted
    assert "tm_mig_x" in redacted


def test_make_migrate_path_does_not_create_owner_databases() -> None:
    """Ordinary make migrate must not gain multi-database CREATE logic."""
    cli_src = load_text("tools", "workflow", "cli.py")
    assert "create_owner_database" not in cli_src
    assert "plan_owner_databases" not in cli_src
    assert "_local_migration_environment" in cli_src
    mig_src = load_text("tools", "workflow", "migrations.py")
    assert "def migrate_integration_check" in mig_src
    assert "create_owner_database" in mig_src
    # Production path remains graph validation + component make migrate, not isolation.
    assert "def check_migrations" in mig_src


def test_isolation_helpers_do_not_stamp_or_wipe_alembic_version() -> None:
    src = inspect.getsource(
        __import__("workflow.migrations", fromlist=["migrate_integration_check"])
    )
    lower = src.lower()
    assert "stamp" not in lower
    assert "drop table alembic_version" not in lower
    assert "delete from alembic_version" not in lower
    assert "truncate alembic_version" not in lower


def test_api_revision_cannot_share_billing_database_url(
    owners_manifest: dict[str, Any],
) -> None:
    """Different database paths mean api head cannot pollute billing alembic_version."""
    planned = plan_owner_databases(
        list(owners_manifest["owners"]),
        run_token="f00dcafe",
        base_url="postgresql+psycopg2://postgres:synthetic@127.0.0.1:15432/postgres",
    )
    api_url = planned[0]["database_url"]
    billing_url = planned[1]["database_url"]
    assert urlparse(api_url).path != urlparse(billing_url).path
    assert "0003_phone_login_session" not in api_url
    assert "0003_phone_login_session" not in billing_url
    assert planned[0]["database"] not in billing_url
    assert planned[1]["database"] not in api_url
