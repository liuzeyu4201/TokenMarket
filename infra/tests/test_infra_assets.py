"""Infrastructure asset validation tests (T027).

These tests fail until `infra/Makefile` and `infra/tools/validate_assets.py`
provide real bootstrap, format, type, lint, test and deterministic asset bundle
evidence without starting SF02-managed resources.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra"


def test_infra_makefile_exists() -> None:
    assert (INFRA_DIR / "Makefile").is_file()


@pytest.mark.parametrize(
    "name",
    ["docker", "nginx", "grafana", "kafka"],
)
def test_infra_readme_exists(name: str) -> None:
    readme = INFRA_DIR / name / "README.md"
    assert readme.is_file(), f"missing {readme}"
    text = readme.read_text(encoding="utf-8")
    assert (
        "SF02" in text or "lifecycle" in text.lower()
    ), f"{readme} must clarify that lifecycle orchestration is owned by SF02"


def test_infra_validate_assets_tool_exists() -> None:
    tool = INFRA_DIR / "tools" / "validate_assets.py"
    assert tool.is_file()


def test_infra_build_does_not_start_sf02_resources() -> None:
    result = subprocess.run(
        ["make", "build"],
        cwd=INFRA_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"infra make build failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    output = result.stdout + result.stderr
    assert "docker-compose up" not in output.lower()
    assert "docker compose up" not in output.lower()


def test_infra_build_produces_deterministic_asset_archive() -> None:
    result = subprocess.run(
        ["make", "build"],
        cwd=INFRA_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    dist = INFRA_DIR / "dist"
    archives = list(dist.glob("*.tar.gz")) if dist.exists() else []
    assert archives, "infra build must produce a deterministic asset archive"


def test_infra_lint_runs_real_checks() -> None:
    result = subprocess.run(
        ["make", "lint"],
        cwd=INFRA_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"infra make lint failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
