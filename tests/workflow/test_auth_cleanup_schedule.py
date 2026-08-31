"""Auth cleanup schedule contract (T090 / T096).

Asserts UTC minute-17 hourly cron, stable module entrypoint, same-version API
image binding, no new public Make actions, and 2h/4h alert linkage.
"""

from __future__ import annotations

from pathlib import Path

from .helpers import find_repo_root, load_text, repo_path

REPO = find_repo_root()
SCHEDULE = repo_path("ops", "schedules", "authentication-cleanup.yml")
COMPOSE_DEPLOY = repo_path("infra", "docker", "compose.deploy.yml")
MAKEFILE = repo_path("Makefile")
ALERTS = repo_path("ops", "alerts", "authentication.yml")

ENTRYPOINT = "python -m app.maintenance.auth_cleanup " "--batch-size 500 --max-runtime-seconds 900"
CRON = "17 * * * *"


def test_schedule_file_exists() -> None:
    assert SCHEDULE.is_file()


def test_cron_is_utc_minute_17_hourly() -> None:
    text = SCHEDULE.read_text(encoding="utf-8")
    assert CRON in text
    assert "UTC" in text or "timezone: UTC" in text


def test_command_matches_stable_entrypoint() -> None:
    text = SCHEDULE.read_text(encoding="utf-8")
    # Allow YAML folding; require the module path and both flags.
    assert "python -m app.maintenance.auth_cleanup" in text
    assert "--batch-size 500" in text or '--batch-size "500"' in text or "--batch-size\n" in text
    assert "500" in text
    assert "900" in text
    assert "max-runtime-seconds" in text
    # Collapsed entrypoint field for exact match when present.
    if "entrypoint:" in text:
        collapsed = " ".join(text.split())
        assert (
            "python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900"
            in collapsed
        )


def test_test_and_prod_only_local_disabled() -> None:
    text = SCHEDULE.read_text(encoding="utf-8")
    assert "test" in text
    assert "prod" in text
    assert "local:" in text
    assert "enabled: false" in text or "manual_only: true" in text


def test_same_version_api_image() -> None:
    text = SCHEDULE.read_text(encoding="utf-8")
    assert "api-service" in text
    assert "same_version" in text or "same-version" in text or "same_version_as" in text


def test_compose_deploy_documents_cleanup_without_default_start() -> None:
    text = COMPOSE_DEPLOY.read_text(encoding="utf-8")
    assert "app.maintenance.auth_cleanup" in text
    assert "--batch-size" in text
    assert "500" in text
    assert "900" in text
    assert "17 * * * *" in text or "authentication-cleanup" in text
    # Profile-gated so default deploy does not run cleanup as a long-lived service.
    if "auth-cleanup:" in text:
        assert 'profiles: ["auth-cleanup"]' in text or "profiles:" in text


def test_no_new_public_make_cleanup_action() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    # Public targets must not grow an auth-cleanup / cleanup action.
    for forbidden in (
        "auth-cleanup",
        "authentication-cleanup",
        "auth_cleanup",
        "cleanup-auth",
    ):
        # Comments may mention cleanup; phony/recipe targets must not.
        for line in makefile.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if forbidden in stripped and (
                stripped.startswith(".PHONY")
                or stripped.endswith(":")
                or stripped.startswith(forbidden)
            ):
                raise AssertionError(f"public Make must not expose {forbidden}: {stripped}")


def test_alerts_reference_2h_and_4h_cleanup_windows() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    assert "7200" in text or "2h" in text or ">2h" in text or "2 h" in text
    assert "14400" in text or "4h" in text or ">4h" in text
    assert "cleanup" in text.lower()
