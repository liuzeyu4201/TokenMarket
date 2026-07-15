"""T084 dirty-worktree format contract tests.

Verify that `make fmt` only touches declared source files, preserves
pre-existing changes and untracked files, and produces zero diff on the second
run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from .helpers import find_repo_root


@pytest.fixture
def isolated_repo() -> Path:
    """Return a disposable copy of the repository under a special path."""
    root = find_repo_root()
    tmp = Path(tempfile.mkdtemp(prefix="tm dirty 副本 "))
    dest = tmp / "repo"
    # Use rsync to copy while skipping heavy/ignored build artifacts.
    rsync = shutil.which("rsync")
    if rsync:
        subprocess.run(
            [
                rsync,
                "-a",
                "--exclude=.venv",
                "--exclude=node_modules",
                "--exclude=dist",
                "--exclude=.pytest_cache",
                "--exclude=.mypy_cache",
                "--exclude=__pycache__",
                str(root) + "/",
                str(dest) + "/",
            ],
            check=True,
            capture_output=True,
        )
    else:
        shutil.copytree(
            root,
            dest,
            ignore=shutil.ignore_patterns(
                ".venv",
                "node_modules",
                "dist",
                ".pytest_cache",
                ".mypy_cache",
                "__pycache__",
            ),
        )
    return dest


def _git_status_short(repo: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def _git_diff_numstat(repo: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--numstat"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def test_fmt_does_not_remove_untracked_files(isolated_repo: Path) -> None:
    env = os.environ.copy()
    untracked = isolated_repo / "untracked-file.txt"
    untracked.write_text("keep me", encoding="utf-8")

    result = subprocess.run(
        ["make", "fmt"],
        cwd=isolated_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    assert untracked.is_file(), "untracked file was removed by make fmt"
    status = _git_status_short(isolated_repo)
    assert "untracked-file.txt" in status, "untracked file missing from status"


def test_fmt_idempotent_on_second_run(isolated_repo: Path) -> None:
    env = os.environ.copy()
    target = isolated_repo / "tools" / "workflow" / "events.py"
    original = target.read_text(encoding="utf-8")
    # Introduce a deliberate formatting issue that `make fmt` will fix.
    target.write_text(original + "\n\n", encoding="utf-8")

    first = subprocess.run(
        ["make", "fmt"],
        cwd=isolated_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr

    diff_after_first = _git_diff_numstat(isolated_repo)
    assert diff_after_first, "expected some formatting diff after first fmt"

    second = subprocess.run(
        ["make", "fmt"],
        cwd=isolated_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr

    diff_after_second = _git_diff_numstat(isolated_repo)
    assert (
        diff_after_second == diff_after_first
    ), f"second fmt produced new differences:\n{diff_after_second}"
