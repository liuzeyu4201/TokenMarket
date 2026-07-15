"""Shared helpers for repository workflow tests.

All helpers operate on repository-relative paths and avoid depending on the
caller's working directory. They are intentionally small and use only the
Python standard library so the workflow test suite can run before the
repository workflow tooling itself is fully implemented.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def find_repo_root() -> Path:
    """Return the repository root by locating the nearest `.git` directory."""
    path = Path(__file__).resolve()
    for parent in [path, *path.parents]:
        if (parent / ".git").is_dir():
            return parent
    raise RuntimeError("Could not locate repository root (.git directory not found)")


def repo_path(*parts: str) -> Path:
    """Resolve a path relative to the repository root."""
    return find_repo_root().joinpath(*parts)


def load_json(*parts: str) -> Any:
    """Load a JSON file from a repository-relative path."""
    with repo_path(*parts).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(*parts: str) -> str:
    """Load a text file from a repository-relative path."""
    with repo_path(*parts).open("r", encoding="utf-8") as fh:
        return fh.read()


def run(
    args: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the completed process.

    The command output is captured and returned as text. Secrets must never be
    passed through this helper.
    """
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )
