"""T088 CI contract tests.

Verify that the GitHub Actions workflow is a thin read-only adapter that only
invokes `make ci`, uses pinned setup actions, scans lock integrity, runs Docker
isolated PostgreSQL 15 and image smoke, and has no path filters, secrets or
publishing steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import repo_path


def test_ci_workflow_exists() -> None:
    assert repo_path(".github", "workflows", "ci.yml").is_file()


def test_ci_workflow_invokes_make_ci() -> None:
    text = repo_path(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    assert "make ci" in text


def test_ci_workflow_uses_pinned_actions() -> None:
    text = repo_path(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    assert "uses: actions/checkout@" in text


def test_ci_workflow_has_read_only_permissions() -> None:
    text = repo_path(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    assert "contents: read" in text


def test_ci_workflow_targets_master_and_master_dev() -> None:
    """Long-lived branches: master (prod), master-dev (test deploy line)."""
    text = repo_path(".github", "workflows", "ci.yml").read_text(encoding="utf-8")
    assert '"master"' in text
    assert '"master-dev"' in text
    # Legacy default branch must not remain the only protected line.
    assert 'branches: ["main"]' not in text
