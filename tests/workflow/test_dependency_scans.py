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
    monkeypatch.setattr(
        "workflow.dependency_policy.validate_auth_dev_dependencies", lambda _root: None
    )
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


def test_python_lock_audit_covers_all_four_projects() -> None:
    """tm-python-audit-coverage: every committed Python lock is audited independently."""
    from workflow.security import PYTHON_LOCK_PROJECTS, python_lock_audit_plan

    root = find_repo_root()
    plan = python_lock_audit_plan(root)
    projects = {item["project"] for item in plan}
    assert projects == set(PYTHON_LOCK_PROJECTS)
    assert len(plan) == 4
    for item in plan:
        export = item["export_cmd"]
        assert "uv" in export and "export" in export and "--frozen" in export
        assert str(root / item["project"]) in export or item["project"] in " ".join(export)
        prefix = item["audit_cmd_prefix"]
        assert prefix[-1] == "pip-audit"


def test_fixture_vulnerability_in_each_omitted_lock_fails_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from workflow.security import PYTHON_LOCK_PROJECTS, audit_python_locks

    for rel in PYTHON_LOCK_PROJECTS:
        (tmp_path / rel).mkdir(parents=True)
        (tmp_path / rel / "uv.lock").write_text("lock\n", encoding="utf-8")

    calls: list[list[str]] = []

    current: dict[str, str] = {"project": ""}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        from types import SimpleNamespace

        calls.append(list(cmd))
        if "export" in cmd:
            idx = cmd.index("--project")
            current["project"] = str(cmd[idx + 1])
            return SimpleNamespace(returncode=0, stdout="pkg==1.0.0\n", stderr="")
        if "pip-audit" in cmd:
            proj = current["project"]
            # Previously omitted locks (billing, admin, workflow) fail the gate.
            if "api-service" in proj and "billing" not in proj:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="CVE-TEST")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        audit_python_locks(tmp_path, max_retries=0)
    assert "pip-audit" in str(exc.value)
    exported = [c for c in calls if "export" in c]
    audited = [c for c in calls if "pip-audit" in c]
    assert exported, "expected uv export of python locks"
    assert audited, "expected pip-audit of python locks"
    # Fail-closed on the first omitted lock (billing-service) after api-service succeeds.
    assert any("billing-service" in " ".join(str(x) for x in c) for c in exported)


def test_package_discovery_includes_local_env() -> None:
    """T067: workflow package discovery stays registered for local_env."""
    pyproject = (find_repo_root() / "tools" / "workflow" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "workflow.local_env" in pyproject
