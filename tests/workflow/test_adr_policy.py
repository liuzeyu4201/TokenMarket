"""T072 ADR policy tests.

Verify that architecture decisions are recorded when adding services, storage,
protocols, shared abstractions or cross-service dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .helpers import repo_path


def test_decisions_directory_exists() -> None:
    assert repo_path("docs", "decisions").is_dir()


def test_decisions_readme_exists() -> None:
    readme = repo_path("docs", "decisions", "README.md")
    assert readme.is_file()
    assert readme.stat().st_size > 0


def test_ci_adr_exists() -> None:
    assert repo_path("docs", "decisions", "001-github-actions-ci-adapter.md").is_file()
