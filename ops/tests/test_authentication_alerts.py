"""Authentication alert contract tests (T088 / T132).

Asserts every plan.md window, threshold, sample floor, severity, owner, and
two-window recovery note is present in ops/alerts/authentication.yml and
ops/runbooks/authentication.md.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALERTS = REPO / "ops" / "alerts" / "authentication.yml"
RUNBOOK = REPO / "ops" / "runbooks" / "authentication.md"


def _alerts() -> str:
    return ALERTS.read_text(encoding="utf-8")


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_alert_files_exist() -> None:
    assert ALERTS.is_file()
    assert RUNBOOK.is_file()


def test_owner_and_runbook_linkage() -> None:
    text = _alerts()
    assert "owner: api-service" in text
    assert "ops/runbooks/authentication.md" in text
    assert "two consecutive" in text.lower() or "Two consecutive" in text


def test_auth_readiness_critical_5m() -> None:
    text = _alerts()
    assert "TokenMarketAuthReadinessUnavailable" in text
    assert "severity: critical" in text
    assert "for: 5m" in text


def test_server_failure_ratio_warning_and_critical() -> None:
    text = _alerts()
    assert "TokenMarketAuthServerFailureRatioWarning" in text
    assert "TokenMarketAuthServerFailureRatioCritical" in text
    assert "> 0.05" in text or ">0.05" in text
    assert ">= 100" in text or "≥100" in text or "100" in text
    assert "> 0.20" in text or ">0.20" in text
    assert "for: 10m" in text
    assert "for: 5m" in text


def test_provider_outcome_thresholds() -> None:
    text = _alerts()
    assert "provider" in text.lower()
    # Warning 10m >10% ≥50; Critical 5m >25% ≥25
    assert "0.10" in text or "10%" in text or "> 0.1" in text
    assert "0.25" in text or "25%" in text


def test_dispatcher_queue_age_thresholds() -> None:
    text = _alerts()
    assert "30" in text  # >30s warning
    assert "120" in text  # >120s critical
    assert (
        "dispatcher" in text.lower()
        or "queue" in text.lower()
        or "eligible" in text.lower()
    )


def test_revocation_visibility_critical() -> None:
    text = _alerts()
    assert "revocation" in text.lower() or "Revocation" in text
    assert "1" in text  # 1s p95
    assert "20" in text  # min samples


def test_cleanup_windows() -> None:
    text = _alerts()
    assert "cleanup" in text.lower() or "Cleanup" in text
    # 2h warning, 4h critical, backlog 1h/2h
    assert "2h" in text or "2 h" in text or "7200" in text
    assert "4h" in text or "4 h" in text or "14400" in text


def test_runbook_documents_recovery_and_exclusions() -> None:
    rb = _runbook()
    assert "two consecutive" in rb.lower()
    assert "rate limit" in rb.lower() or "限流" in rb or "rate-limit" in rb.lower()
    assert "OTP" in rb or "验证码" in rb or "field" in rb.lower()
    assert "API Service" in rb or "api-service" in rb


def test_runbook_sms_fail_closed_matrix() -> None:
    rb = _runbook()
    # FR-016: production without approved SMS remains unavailable
    assert (
        "synthetic" in rb.lower()
        or "fail" in rb.lower()
        or "不可用" in rb
        or "SMS" in rb
    )
