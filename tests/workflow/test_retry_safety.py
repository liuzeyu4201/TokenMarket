"""T086 retry safety contract tests.

Verify that a failed workflow run can be safely retried without mutating the
worktree, except for fmt which is expected to modify declared source files.
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
    tmp = Path(tempfile.mkdtemp(prefix="tm retry 副本 "))
    dest = tmp / "repo"
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


def test_non_fmt_actions_do_not_mutate_worktree(isolated_repo: Path) -> None:
    """A failed lint run leaves pre-existing user changes intact."""
    env = os.environ.copy()
    # Introduce a Python syntax error in a component to force lint failure.
    target = isolated_repo / "services" / "api-service" / "app" / "main.py"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\ndef _broken_syntax(\n", encoding="utf-8")

    status_before = _git_status_short(isolated_repo)

    result = subprocess.run(
        ["make", "lint"],
        cwd=isolated_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "expected lint to fail due to injected syntax error"

    status_after = _git_status_short(isolated_repo)
    assert (
        status_before == status_after
    ), f"lint failure mutated worktree:\nbefore:\n{status_before}\nafter:\n{status_after}"
