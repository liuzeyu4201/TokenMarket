"""SF32 SLO alert contract tests."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALERTS = REPO / "ops" / "alerts" / "slo.yml"
RUNBOOK = REPO / "ops" / "runbooks" / "slo-alerts.md"
DASH = (
    REPO / "infra" / "grafana" / "provisioning" / "dashboards" / "v02-slo-overview.json"
)


def test_files_exist() -> None:
    assert ALERTS.is_file()
    assert RUNBOOK.is_file()
    assert DASH.is_file()


def test_five_alerts_have_runbook_owner_escalation() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    for name in (
        "TokenMarketUpstreamSlow",
        "TokenMarketNoRouteCandidate",
        "TokenMarketEventBacklog",
        "TokenMarketUnresolvedSpike",
        "TokenMarketConnectionUnhealthy",
    ):
        assert name in text, name
    assert "ops/runbooks/slo-alerts.md" in text
    assert "v02-slo-overview" in text
    assert "P1 on-call" in text
    assert "owner: proxy-gateway" in text
    assert "owner: billing-service" in text
    assert "owner: supply_ops" in text
    assert "> 2" in text
    assert "> 1000" in text
    assert "> 10" in text


def test_runbook_covers_kinds() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for kind in (
        "upstream_slow",
        "no_candidate",
        "event_backlog",
        "unresolved_spike",
        "connection_unhealthy",
    ):
        assert kind in text
    assert "冻结发布" in text
    assert "request_id" in text


def test_dashboard_has_slo_panels() -> None:
    text = DASH.read_text(encoding="utf-8")
    for title in (
        "Dataplane availability",
        "Admin availability",
        "Dataplane error budget remaining",
        "Platform vs upstream latency",
        "SSE first event",
        "Event backlog",
        "Unresolved cases",
        "Connection health",
    ):
        assert title in text, title
    assert "request_id" not in text
    assert "api_key" not in text
    assert "user_id" not in text
