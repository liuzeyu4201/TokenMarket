"""SF02 transition tests for `make dev` and `make dev-down`.

SF01 must block the local dependency lifecycle targets because real dependency
orchestration is owned by feature SF02. These tests verify that the root Makefile
fails with the stable diagnostic code `SF02_NOT_READY` before reading
configuration, checking Docker, or mutating the workspace.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Set

import pytest

from .helpers import find_repo_root, repo_path, run

SF02_CODE = "SF02_NOT_READY"


def _root_snapshot() -> Set[str]:
    """Return a snapshot of repository-root entries before a side-effect test."""
    root = find_repo_root()
    return {str(p.relative_to(root)) for p in root.iterdir()}


def _run_make(
    target: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke a root Make target and capture output."""
    return run(
        ["make", target],
        cwd=find_repo_root(),
        check=False,
    )


def _assert_sf02_block(result: subprocess.CompletedProcess[str], target: str) -> None:
    """Assert that a result represents a clean SF02_NOT_READY failure."""
    output = result.stdout + result.stderr
    assert (
        result.returncode != 0
    ), f"make {target} must fail before SF02; expected non-zero exit, got 0"
    assert SF02_CODE in output, (
        f"make {target} must emit {SF02_CODE}; got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_dev_fails_with_sf02_not_ready() -> None:
    """`make dev` must fail immediately with SF02_NOT_READY."""
    result = _run_make("dev")
    _assert_sf02_block(result, "dev")


def test_dev_down_fails_with_sf02_not_ready() -> None:
    """`make dev-down` must fail immediately with SF02_NOT_READY."""
    result = _run_make("dev-down")
    _assert_sf02_block(result, "dev-down")


def test_dev_does_not_read_configuration() -> None:
    """`make dev` must fail with SF02_NOT_READY before reading real env files."""
    root = find_repo_root()
    allowed = {".env.example", ".env.local.example"}
    for env_file in root.glob(".env*"):
        if env_file.name in allowed or env_file.name.endswith(".example"):
            continue
        # Real .env files must not be present in a fresh checkout; if they are,
        # the workspace has already been mutated and the test cannot prove the
        # pre-config failure order.
        pytest.fail(f"unexpected environment file in repository root: {env_file}")

    result = _run_make("dev")
    _assert_sf02_block(result, "dev")
    assert (
        "INVALID_CONFIG" not in result.stdout + result.stderr
    ), "dev must fail with SF02_NOT_READY before any configuration validation"


def test_dev_does_not_invoke_docker(tmp_path: Path) -> None:
    """`make dev` must fail before any Docker executable is consulted."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/bin/sh\necho 'FAKE_DOCKER_CALLED' >&2\nexit 99\n")
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

    result = subprocess.run(
        ["make", "dev"],
        cwd=find_repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    _assert_sf02_block(result, "dev")
    assert (
        "FAKE_DOCKER_CALLED" not in result.stdout + result.stderr
    ), "dev must not execute docker before failing with SF02_NOT_READY"


def test_dev_down_has_no_workspace_side_effects() -> None:
    """`make dev-down` must not create, modify or remove repository-root entries."""
    before = _root_snapshot()
    result = _run_make("dev-down")
    after = _root_snapshot()
    _assert_sf02_block(result, "dev-down")
    assert before == after, f"make dev-down changed repository-root entries: {before ^ after}"
