"""Boundary assertions for SF02 scope (T056, US3).

Gateway and Admin must not gain undeclared dependency probes; ``make dev``
must not start business services; and no business route, schema, migration,
or seed behavior is introduced by the SF02 lifecycle package.
"""

from __future__ import annotations

import ast
from pathlib import Path

from workflow.local_env import compose as compose_module
from workflow.local_env.models import parse_manifest

from .helpers import find_repo_root, load_json


def test_gateway_and_admin_have_no_dependency_probes() -> None:
    repo = find_repo_root()
    for service in ("proxy-gateway", "admin-service"):
        service_root = repo / "services" / service
        if not service_root.exists():
            continue
        for path in service_root.rglob("*"):
            if path.suffix not in {".py", ".go", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert "probe_postgres" not in text
            assert "build_readiness_probe" not in text
            assert "postgres_probe" not in text


def test_compose_local_starts_only_three_dependencies() -> None:
    repo = find_repo_root()
    compose_path = repo / "infra" / "docker" / "compose.local.yml"
    text = compose_path.read_text(encoding="utf-8")
    # Service keys only — comments may mention out-of-scope products by name.
    service_keys = []
    in_services = False
    for line in text.splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services and line and not line.startswith(" ") and not line.startswith("\t"):
            break
        if in_services and line.startswith("  ") and not line.startswith("   "):
            key = line.strip().rstrip(":")
            if key and not key.startswith("#"):
                service_keys.append(key)
    assert service_keys == ["postgres", "redis", "grafana"]


def test_manifest_declares_exactly_three_dependencies() -> None:
    manifest = parse_manifest(load_json("ops", "workflow", "local-dependencies.json"))
    assert [dep.id.value for dep in manifest.dependencies] == [
        "postgres",
        "redis",
        "grafana",
    ]


def test_lifecycle_package_has_no_migration_or_seed_side_effects() -> None:
    repo = find_repo_root()
    package = repo / "tools" / "workflow" / "local_env"
    forbidden_tokens = (
        "alembic",
        "CREATE TABLE",
        "INSERT INTO",
        "seed_",
        "run_migrations",
        "schema_migrate",
    )
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{path} must not introduce {token}"


def test_compose_down_never_uses_destructive_volume_flags() -> None:
    source = Path(compose_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"--volumes", "--rmi"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in forbidden
            # Reject a bare prune command token, not prose mentions.
            if node.value == "prune":
                raise AssertionError("compose adapter must never invoke prune")


def test_public_dev_targets_no_longer_emit_sf02_not_ready(monkeypatch, capsys) -> None:
    """T074: public dev/dev-down dispatch the real lifecycle, not SF02_NOT_READY."""
    from workflow import cli as workflow_cli

    class _Outcome:
        status = "PASSED"
        events: list = []
        plain_lines = ["[PASSED] lifecycle probe"]

    async def _fake_start(**kwargs):  # type: ignore[no-untyped-def]
        return _Outcome()

    async def _fake_stop(**kwargs):  # type: ignore[no-untyped-def]
        return _Outcome()

    monkeypatch.setattr("workflow.local_env.lifecycle.start_local_environment", _fake_start)
    monkeypatch.setattr("workflow.local_env.lifecycle.stop_local_environment", _fake_stop)

    for action in ("dev", "dev-down"):
        code = workflow_cli.execute_action(
            action,
            mode=None,
            mode_origin="omitted",
            plain=True,
            repo_root=find_repo_root(),
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "SF02_NOT_READY" not in out


def test_local_compose_never_includes_application_or_deploy_merge() -> None:
    """T083: ADR 003 app/deploy assets must not expand compose.local.yml."""
    repo = find_repo_root()
    local = (repo / "infra" / "docker" / "compose.local.yml").read_text(encoding="utf-8")
    assert "compose.app.yml" not in local
    assert "compose.deploy.yml" not in local
    assert "compose.middleware.yml" not in local
    assert "TOKENMARKET_DEPLOY_" not in local
    for service in (
        "proxy-gateway",
        "api-service",
        "billing-service",
        "admin-service",
        "frontend",
    ):
        assert not __import__("re").search(
            rf"(?m)^\s*{service}\s*:",
            local,
        ), f"compose.local.yml must not define {service}"


def test_local_env_package_does_not_import_deploy_env() -> None:
    """T083: SF02 lifecycle package stays independent of deploy_env."""
    repo = find_repo_root()
    package = repo / "tools" / "workflow" / "local_env"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "deploy_env" not in text, f"{path} must not depend on deploy_env"
        assert "compose.app.yml" not in text
        assert "compose.deploy.yml" not in text
        assert "local_stack" not in text, f"{path} must not depend on local_stack"


def test_local_stack_does_not_expand_compose_local() -> None:
    """local_stack supervises host processes; compose.local stays middleware-only."""
    repo = find_repo_root()
    package = repo / "tools" / "workflow" / "local_stack"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "compose.app.yml" not in text
        assert "compose.deploy.yml" not in text
        assert "deploy_up" not in text


def test_public_dev_does_not_dispatch_deploy_stack(monkeypatch, capsys) -> None:
    """T083: make dev lifecycle path never routes into deploy_up."""
    from workflow import cli as workflow_cli

    class _Outcome:
        status = "PASSED"
        events: list = []
        plain_lines = ["[PASSED] lifecycle probe"]

    async def _fake_start(**kwargs):  # type: ignore[no-untyped-def]
        return _Outcome()

    monkeypatch.setattr("workflow.local_env.lifecycle.start_local_environment", _fake_start)

    code = workflow_cli.execute_action(
        "dev",
        mode=None,
        mode_origin="omitted",
        plain=True,
        repo_root=find_repo_root(),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "SF02_NOT_READY" not in out
    assert "tokenmarket-test" not in out
    assert "compose.deploy" not in out


def test_public_start_dispatches_full_scope(monkeypatch) -> None:
    """T074: 默认 start 走完整 local_stack（中间件 + 应用）。"""
    from workflow import cli as workflow_cli
    from workflow import local_stack

    received: dict[str, object] = {}

    def fake_start(repo_root, **kwargs) -> int:
        received.update(kwargs)
        return 0

    monkeypatch.setenv("TOKENMARKET_START_SCOPE", "all")
    monkeypatch.setattr(local_stack, "start_local", fake_start)

    code = workflow_cli.execute_action(
        "start",
        mode=None,
        mode_origin="omitted",
        plain=True,
        repo_root=find_repo_root(),
    )

    assert code == 0
    assert received["scope"] == "all"


def test_process_only_start_remains_available(monkeypatch) -> None:
    """scope=apps 仍只启动主机进程范围。"""
    from workflow import cli as workflow_cli
    from workflow import local_stack

    received: dict[str, object] = {}

    def fake_start(repo_root, **kwargs) -> int:
        received.update(kwargs)
        return 0

    monkeypatch.setenv("TOKENMARKET_START_SCOPE", "apps")
    monkeypatch.setattr(local_stack, "start_local", fake_start)

    code = workflow_cli.execute_action(
        "start",
        mode=None,
        mode_origin="omitted",
        plain=True,
        repo_root=find_repo_root(),
    )

    assert code == 0
    assert received["scope"] == "apps"


def test_public_stop_dispatches_full_scope(monkeypatch) -> None:
    """T074: 默认 stop 走完整 local_stack 停止路径。"""
    from workflow import cli as workflow_cli
    from workflow import local_stack

    received: dict[str, object] = {}

    def fake_stop(repo_root, **kwargs) -> int:
        received.update(kwargs)
        return 0

    monkeypatch.setenv("TOKENMARKET_START_SCOPE", "all")
    monkeypatch.setattr(local_stack, "stop_local", fake_stop)

    code = workflow_cli.execute_action(
        "stop",
        mode=None,
        mode_origin="omitted",
        plain=True,
        repo_root=find_repo_root(),
    )

    assert code == 0
    assert received["scope"] == "all"


def test_config_rejects_remote_and_wildcard_endpoints() -> None:
    """T067: non-loopback and wildcard hosts fail closed before Docker."""
    import pytest

    from workflow.local_env.config import InvalidConfigError, parse_local_environment

    secret = "tm_local_" + ("c" * 32)
    remote = (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://app:{secret}@8.8.8.8:5432/tokenmarket\n"
        f"REDIS_URL=redis://default:{secret}@127.0.0.1:6379/0\n"
        f"GRAFANA_URL=http://127.0.0.1:3000\n"
        f"GRAFANA_ADMIN_PASSWORD={secret}\n"
    )
    with pytest.raises(InvalidConfigError):
        parse_local_environment(remote)

    wildcard = (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://app:{secret}@0.0.0.0:5432/tokenmarket\n"
        f"REDIS_URL=redis://default:{secret}@127.0.0.1:6379/0\n"
        f"GRAFANA_URL=http://127.0.0.1:3000\n"
        f"GRAFANA_ADMIN_PASSWORD={secret}\n"
    )
    with pytest.raises(InvalidConfigError):
        parse_local_environment(wildcard)
