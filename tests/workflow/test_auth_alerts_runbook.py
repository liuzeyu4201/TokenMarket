"""Auth alerts + runbook structural coverage (T088 / T097)."""

from __future__ import annotations

from .helpers import find_repo_root, repo_path

REPO = find_repo_root()
ALERTS = repo_path("ops", "alerts", "authentication.yml")
RUNBOOK = repo_path("ops", "runbooks", "authentication.md")

REQUIRED_SIGNAL_MARKERS = [
    # readiness
    "readiness",
    # server / dependency failure ratio thresholds
    "0.05",
    "0.20",
    "100",
    "50",
    # provider failure
    "provider",
    "0.10",
    "0.25",
    # dispatcher queue age
    "30",
    "120",
    "dispatcher",
    # revocation
    "revocation",
    # cleanup
    "cleanup",
    "7200",  # 2h
    "14400",  # 4h
    # backlog
    "3600",  # 1h
    "7200",  # 2h (also last-success critical shares 7200 in some forms)
    # redis
    "redis",
    # owner + runbook
    "owner: api-service",
    "ops/runbooks/authentication.md",
]

REQUIRED_ALERT_NAMES = [
    "TokenMarketAuthReadinessUnavailable",
    "TokenMarketAuthServerFailureRatioWarning",
    "TokenMarketAuthServerFailureRatioCritical",
    "TokenMarketAuthProviderFailureRatioWarning",
    "TokenMarketAuthProviderFailureRatioCritical",
    "TokenMarketAuthDispatcherQueueAgeWarning",
    "TokenMarketAuthDispatcherQueueAgeCritical",
    "TokenMarketAuthRevocationVisibilityCritical",
    "TokenMarketAuthCleanupFailureWarning",
    "TokenMarketAuthCleanupFailureCritical",
    "TokenMarketAuthCleanupBacklogWarning",
    "TokenMarketAuthCleanupBacklogCritical",
    "TokenMarketAuthRedisUnavailable",
]


def test_alerts_file_exists() -> None:
    assert ALERTS.is_file()


def test_runbook_file_exists() -> None:
    assert RUNBOOK.is_file()


def test_required_alert_rules_present() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    for name in REQUIRED_ALERT_NAMES:
        assert name in text, f"missing alert {name}"


def test_required_signal_markers_present() -> None:
    text = ALERTS.read_text(encoding="utf-8").lower()
    # Case-sensitive markers checked separately where needed.
    raw = ALERTS.read_text(encoding="utf-8")
    for marker in REQUIRED_SIGNAL_MARKERS:
        if marker.startswith("owner:") or marker.startswith("ops/"):
            assert marker in raw, f"missing marker {marker}"
        else:
            assert marker.lower() in text, f"missing marker {marker}"


def test_warning_and_critical_severities() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    assert "severity: warning" in text
    assert "severity: critical" in text


def test_two_window_recovery_documented() -> None:
    text = ALERTS.read_text(encoding="utf-8").lower()
    assert "two consecutive" in text or "two-window" in text or "two window" in text


def test_runbook_owner_diagnosis_rollback() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "API Service" in text
    assert "Owner" in text or "owner" in text
    # Diagnosis surfaces
    for needle in ("PostgreSQL", "Redis", "dispatcher", "cleanup", "provider"):
        assert needle.lower() in text.lower(), f"runbook missing diagnosis for {needle}"
    # Rollback keeps data
    assert "keep" in text.lower() or "intact" in text.lower() or "additive" in text.lower()
    assert "rollback" in text.lower() or "Rollback" in text
    # Entrypoint
    assert "python -m app.maintenance.auth_cleanup" in text
    assert "--batch-size 500" in text
    assert "--max-runtime-seconds 900" in text


def test_runbook_links_alerts() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "ops/alerts/authentication.yml" in text
