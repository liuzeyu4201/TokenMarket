"""SF05 structural gates for HA deploy assets."""

from __future__ import annotations

from .helpers import load_text, repo_path


APP_SERVICES = (
    "proxy-gateway",
    "api-service",
    "billing-service",
    "admin-service",
    "frontend",
)


def test_app_compose_has_no_build_keys() -> None:
    text = load_text("infra", "docker", "compose.app.yml")
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("build:") and not stripped.startswith("#"):
            raise AssertionError(f"build key not allowed: {line!r}")
        if line.startswith("    build:") or line.startswith("  build:"):
            raise AssertionError(f"service build key not allowed: {line!r}")


def test_app_services_have_health_and_grace() -> None:
    text = load_text("infra", "docker", "compose.app.yml")
    for name in APP_SERVICES:
        assert f"  {name}:" in text
    assert text.count("healthcheck:") >= 5
    assert text.count("stop_grace_period:") >= 5
    assert "stop_grace_period: 30s" in text


def test_deploy_down_source_retains_volumes() -> None:
    life = load_text("tools", "workflow", "deploy_env", "lifecycle.py")
    lowered = life.lower()
    assert "never delete volumes" in lowered or "volumes retained" in lowered
    runbook = load_text("ops", "runbooks", "deploy.md")
    assert "--volumes" in runbook
    assert "must never pass `--volumes`" in runbook or "never pass `--volumes`" in runbook


def test_ha_runbook_rpo_rto() -> None:
    rollout = load_text("ops", "runbooks", "ha-rollout.md")
    restore = load_text("ops", "backup", "postgres-restore.md")
    assert "mode=test" in rollout and "mode=prod" in rollout
    assert "RPO" in restore and "5" in restore
    assert "RTO" in restore and "30" in restore
    assert "--volumes" in rollout
    assert repo_path("ops", "runbooks", "ha-rollout.md").is_file()
