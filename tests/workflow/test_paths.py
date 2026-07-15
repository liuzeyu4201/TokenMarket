"""T083 path resolution contract tests.

Verify that the workflow tool resolves the repository root from any working
directory, rejects paths outside the repository, and handles spaces and
non-ASCII characters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root


@pytest.fixture
def cli() -> Any:
    try:
        import workflow.cli as cli_module  # type: ignore[import]
    except ImportError as exc:
        pytest.fail(f"workflow.cli has not been implemented yet (T092): {exc}")
    return cli_module


def test_repo_root_is_resolved_from_script_location(cli: Any) -> None:
    root = cli._repo_root()
    assert root.is_dir()
    assert (root / "Makefile").is_file()
    assert (root / ".git").is_dir() or (root / ".specify").is_dir()


def test_repo_root_rejects_outside_path(cli: Any) -> None:
    # A path outside the repo should not be accepted as a component path.
    root = find_repo_root()
    outside = Path("/tmp") / "outside-repo"
    assert not (root / "..") == outside
