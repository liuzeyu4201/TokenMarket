"""T056 configuration definition contract tests.

Verify that `.env.example` declares all required SF01 configuration variables
with safe placeholders and that `.gitignore` rejects local `.env.*` files while
allowing safe `.example` definitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, repo_path


def test_env_example_exists() -> None:
    assert repo_path(".env.example").is_file()


def test_env_example_declares_mode_variable() -> None:
    env = repo_path(".env.example").read_text(encoding="utf-8")
    assert "MODE=" in env
    assert "local" in env


def test_env_example_uses_safe_placeholders() -> None:
    env = repo_path(".env.example").read_text(encoding="utf-8")
    # No real-looking URLs, passwords or keys in the example file.
    assert "tokenmarket.local" not in env.lower() or "example.local" in env.lower()
    assert "mysecret" not in env.lower()
    assert "admin123" not in env.lower()


def test_env_example_declares_database_url_placeholder() -> None:
    env = repo_path(".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL=" in env
    assert "replace-me" in env or "<" in env


def test_gitignore_rejects_env_files() -> None:
    gitignore = repo_path(".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".env.*" in gitignore


def test_gitignore_allows_example_definitions() -> None:
    gitignore = repo_path(".gitignore").read_text(encoding="utf-8")
    assert "!.env.example" in gitignore or "!.env.*.example" in gitignore
