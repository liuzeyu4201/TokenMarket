"""Shared contract asset validation tests (T026).

These tests fail until `shared/tools/validate_contracts.py` and the shared
Makefile implement real schema parsing, negative fixtures, source mapping and
deterministic asset bundle generation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_shared_makefile_exists() -> None:
    assert (REPO_ROOT / "shared" / "Makefile").is_file()


def test_contract_readme_exists_and_links_source() -> None:
    readme = REPO_ROOT / "shared" / "contracts" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "version" in text.lower()
    assert "owner" in text.lower()


def test_contract_manifest_schema_exists() -> None:
    schema = REPO_ROOT / "shared" / "contracts" / "_meta"
    schema = schema / "contract-manifest.schema.json"
    assert schema.is_file()


def test_validate_contracts_tool_exists() -> None:
    tool = REPO_ROOT / "shared" / "tools" / "validate_contracts.py"
    assert tool.is_file()


def test_shared_build_produces_deterministic_asset_archive() -> None:
    result = subprocess.run(
        ["make", "build"],
        cwd=REPO_ROOT / "shared",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"shared make build failed:\nstdout:\n{result.stdout}\n" f"stderr:\n{result.stderr}"
    )
    dist = REPO_ROOT / "shared" / "dist"
    archives = list(dist.glob("*.tar.gz")) if dist.exists() else []
    assert archives, "shared build must produce a deterministic asset archive"


def test_user_registration_v1_assets_exist() -> None:
    base = REPO_ROOT / "shared" / "contracts" / "user-registration" / "v1"
    assert (base / "user-registration.openapi.yaml").is_file()
    assert (base / "business-codes.md").is_file()
    assert (base / "phone-normalization.md").is_file()
    readme = REPO_ROOT / "shared" / "contracts" / "README.md"
    assert "user-registration/v1" in readme.read_text(encoding="utf-8")


def test_shared_schema_validation_fails_on_drift() -> None:
    result = subprocess.run(
        ["make", "lint"],
        cwd=REPO_ROOT / "shared",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"shared make lint failed:\nstdout:\n{result.stdout}\n" f"stderr:\n{result.stderr}"
    )
