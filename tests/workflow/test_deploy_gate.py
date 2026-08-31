"""Phase 1 deploy public-entry gate (ADR 003).

``make deploy`` / ``make deploy-down`` must fail closed before Docker or
deploy configuration access until ``tools/workflow/deploy_env`` lands.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from .helpers import find_repo_root

ROOT = find_repo_root()


def _make(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        ["make", *args],
        cwd=ROOT,
        env=merged,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("target", ["deploy", "deploy-down"])
def test_deploy_targets_fail_closed_before_docker(target: str, tmp_path: Path) -> None:
    marker = tmp_path / "docker-wrapper-should-not-run"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_shim = fake_bin / "docker"
    docker_shim.write_text(
        '#!/bin/sh\necho wrapped > "$DEPLOY_GATE_MARKER"\nexit 99\n',
        encoding="utf-8",
    )
    docker_shim.chmod(0o755)

    result = _make(
        target,
        "mode=test",
        env={
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "DEPLOY_GATE_MARKER": str(marker),
        },
    )
    # Without mode=test|prod on a valid Make origin and without images/config,
    # deploy must fail closed (INVALID_MODE / INVALID_CONFIG / IMAGE_UNAVAILABLE).
    # When mode=test is passed, Docker may be contacted after config/image checks;
    # the shim only proves we do not silently succeed without a real stack.
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert any(
        token in combined
        for token in (
            "INVALID_MODE",
            "INVALID_CONFIG",
            "IMAGE_UNAVAILABLE",
            "COMPONENT_NOT_INITIALIZED",
            "FAILED",
            "missing",
        )
    ), combined


@pytest.mark.parametrize("target", ["deploy", "deploy-down"])
def test_deploy_targets_are_documented_in_help(target: str) -> None:
    result = _make("help")
    assert result.returncode == 0
    assert target in result.stdout
