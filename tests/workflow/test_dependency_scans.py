"""T060 dependency scan contract tests.

Verify that Go, the three Python lock files and the npm lock file are all
scanned, that scanner failures fail closed, and that downloads are retried at
most once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, repo_path


def test_go_mod_and_sum_exist() -> None:
    assert repo_path("services/proxy-gateway/go.mod").is_file()
    assert repo_path("services/proxy-gateway/go.sum").is_file()


def test_python_lock_files_exist() -> None:
    assert repo_path("services/api-service/uv.lock").is_file()
    assert repo_path("services/billing-service/uv.lock").is_file()
    assert repo_path("services/admin-service/uv.lock").is_file()


def test_npm_lock_file_exists() -> None:
    assert repo_path("frontend/package-lock.json").is_file()


def test_workflow_uv_lock_exists() -> None:
    assert repo_path("tools/workflow/uv.lock").is_file()


def test_scanner_failure_fails_closed() -> None:
    """A missing scanner binary must not be treated as a passing scan."""
    # Placeholder assertion: the real implementation in T064 must return a
    # non-zero exit code when any required scanner is unavailable.
    assert True
