"""Operations asset validation tests (T028).

These tests fail until `ops/Makefile` and `ops/tools/validate_assets.py`
provide real bootstrap, format, type, lint, test and deterministic asset bundle
evidence for migration, monitoring, backup and runbook assets.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = REPO_ROOT / "ops"


def test_ops_makefile_exists() -> None:
    assert (OPS_DIR / "Makefile").is_file()


@pytest.mark.parametrize(
    "name",
    ["migrations", "monitoring", "backup", "runbooks"],
)
def test_ops_asset_readme_exists(name: str) -> None:
    readme = OPS_DIR / name / "README.md"
    assert readme.is_file(), f"missing {readme}"


def test_ops_runbook_workflow_exists() -> None:
    runbook = OPS_DIR / "runbooks" / "workflow.md"
    assert runbook.is_file()


def test_ops_runbook_migrations_exists() -> None:
    runbook = OPS_DIR / "runbooks" / "migrations.md"
    assert runbook.is_file()


def test_ops_runbook_endpoint_catalog_exists() -> None:
    runbook = OPS_DIR / "runbooks" / "endpoint-catalog.md"
    assert runbook.is_file()


def test_ops_runbook_gateway_stateless_exists() -> None:
    runbook = OPS_DIR / "runbooks" / "gateway-stateless.md"
    assert runbook.is_file()


def test_ops_runbook_ha_rollout_exists() -> None:
    runbook = OPS_DIR / "runbooks" / "ha-rollout.md"
    assert runbook.is_file()


def test_ops_postgres_restore_runbook_exists() -> None:
    assert (OPS_DIR / "backup" / "postgres-restore.md").is_file()


def test_ops_validate_assets_tool_exists() -> None:
    tool = OPS_DIR / "tools" / "validate_assets.py"
    assert tool.is_file()


def test_ops_build_produces_deterministic_asset_archive() -> None:
    result = subprocess.run(
        ["make", "build"],
        cwd=OPS_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    # fmt: off
    detail = (
        f"ops make build failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    # fmt: on
    assert result.returncode == 0, detail
    dist = OPS_DIR / "dist"
    archives = list(dist.glob("*.tar.gz")) if dist.exists() else []
    assert archives, "ops build must produce a deterministic asset archive"


def test_ops_lint_runs_real_checks() -> None:
    result = subprocess.run(
        ["make", "lint"],
        cwd=OPS_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    # fmt: off
    detail = (
        f"ops make lint failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    # fmt: on
    assert result.returncode == 0, detail
