"""SF19 proxy alert contract tests."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALERTS = REPO / "ops" / "alerts" / "proxy.yml"
DASH = (
    REPO
    / "infra"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "v01-proxy-overview.json"
)


def test_alert_and_dashboard_exist() -> None:
    assert ALERTS.is_file()
    assert DASH.is_file()


def test_system_error_rate_rule() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    assert "TokenMarketProxySystemErrorRateHigh" in text
    assert "> 0.05" in text
    assert ">= 20" in text
    assert "for: 5m" in text
    assert "severity: warning" in text
    assert "owner: proxy-gateway" in text
    assert "ops/runbooks/volcano-openai-compat.md" in text
    assert "client_error" not in text.split("system_error")[0] or "auth_error" in text
    assert "< 0.03" in text
    assert "Two consecutive" in text or "two consecutive" in text.lower()


def test_grafana_alerting_provisioned() -> None:
    path = REPO / "infra" / "grafana" / "provisioning" / "alerting" / "proxy.yaml"
    text = path.read_text(encoding="utf-8")
    assert "TokenMarketProxySystemErrorRateHigh" in text
    assert "0.05" in text
    assert "tokenmarket-prometheus" in text
    assert "for: 5m" in text or "for: 5m" in text.replace(" ", "")
    assert "severity: warning" in text


def test_dashboard_core_panels() -> None:
    text = DASH.read_text(encoding="utf-8")
    for title in (
        "QPS",
        "P95 latency",
        "4xx client error ratio",
        "5xx / upstream system error ratio",
        "Key inventory",
        "Health checks",
        "Usage persist",
    ):
        assert title in text, title
    assert '"refresh": "10s"' in text
    assert "No data / scrape failed" in text
    assert "proxy_requests_total" in text
    assert "provider_key_inventory" in text
