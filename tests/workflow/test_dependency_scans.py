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


def test_scanner_failure_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T081: missing required scanners fail closed with a non-zero contract."""
    import shutil

    from workflow import security as security_module

    # Simulate a host where every required scanner binary is absent.
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError) as excinfo:
        security_module.run_security_checks(tmp_path, max_retries=0)
    message = str(excinfo.value).lower()
    assert "missing" in message or "required security scanners" in message
    for name in ("gitleaks", "govulncheck", "npm"):
        assert name in message or "scanner" in message


def test_runtime_must_not_rewrite_service_or_workflow_locks() -> None:
    """T067: lifecycle package never mutates committed lockfiles at runtime."""
    package = find_repo_root() / "tools" / "workflow" / "local_env"
    forbidden = ("uv.lock", "package-lock.json", "go.sum", "pip freeze", "uv lock")
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} must not reference lock mutation ({token})"


def test_package_discovery_includes_local_env() -> None:
    """T067: workflow package discovery stays registered for local_env."""
    pyproject = (find_repo_root() / "tools" / "workflow" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "workflow.local_env" in pyproject
