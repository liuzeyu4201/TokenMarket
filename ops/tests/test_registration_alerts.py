"""Structural checks for registration Prometheus alert rules."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALERTS = REPO / "ops" / "alerts" / "registration.yml"

REQUIRED_METRICS = [
    "tokenmarket_registration_attempts_total",
    "tokenmarket_rate_limit_backend_unavailable_total",
]


def test_registration_alerts_file_exists() -> None:
    assert ALERTS.is_file()


def test_alerts_reference_known_metrics() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    for metric in REQUIRED_METRICS:
        assert metric in text, f"missing metric {metric}"
    assert "TokenMarketRegistrationHighErrorRate" in text
    assert "owner: api-service" in text
