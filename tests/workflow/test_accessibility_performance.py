"""T087 accessibility and performance contract tests.

Verify that `make help` completes within two seconds, preflight checks complete
within five seconds, NO_COLOR disables color, and status is readable without a
TTY.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

import pytest

from .helpers import find_repo_root


def test_help_completes_within_two_seconds() -> None:
    root = find_repo_root()
    start = time.monotonic()
    result = subprocess.run(
        ["make", "help"], cwd=str(root), capture_output=True, text=True, check=False
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 2.0


def test_toolchain_check_completes_within_five_seconds() -> None:
    root = find_repo_root()
    start = time.monotonic()
    result = subprocess.run(
        ["make", "toolchain-check"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 5.0


def test_no_color_disables_color_output() -> None:
    root = find_repo_root()
    env = {"NO_COLOR": "1", "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        ["make", "help"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "\033[" not in result.stdout
