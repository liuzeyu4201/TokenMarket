"""Migration ownership and round-trip tests (T020).

These tests fail until the migration owner manifest, Alembic graphs, and the
workflow migration checker/executor are implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path, run


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


def test_migrate_integration_check_uses_isolated_database() -> None:
    result = run(["make", "migrate-integration-check"], cwd=find_repo_root(), check=False)
    output = result.stdout + result.stderr
    assert "shared database" not in output.lower()
    assert "make dev" not in output.lower()


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
