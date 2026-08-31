from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.domain.admin import AdminError
from app.domain.slo.alerts import evaluate_alert
from app.domain.slo.budget import WINDOW_SECONDS, snapshot
from app.domain.slo.labels import FORBIDDEN, allow_labels
from app.domain.slo.redact import redact, scan_secrets
from app.domain.slo.trace import TraceHop, TraceLog


def test_request_id_correlates_five_hops_with_async_link() -> None:
    log = TraceLog()
    rid = "rid-slo-1"
    stages = ("proxy", "route", "upstream", "usage", "ledger")
    for i, stage in enumerate(stages):
        kind = "link" if stage in {"usage", "ledger"} else "span"
        svc = "worker" if kind == "link" else "gateway"
        log.append(
            TraceHop(
                request_id=rid,
                service=svc,
                stage=stage,
                kind=kind,
                freshness="live",
                at=datetime(2026, 8, 31, tzinfo=timezone.utc),
            )
        )
        _ = i
    chain = log.correlate(rid)
    assert [h.stage for h in chain] == list(stages)
    assert chain[-1].kind == "link"
    assert chain[-2].kind == "link"
    missing = log.correlate("absent")
    assert missing == [] or all(h.freshness == "unknown" for h in missing)


def test_slo_budget_and_freeze() -> None:
    ok = snapshot(plane="dataplane", good=9995, total=10000)
    assert ok.target == 0.999
    assert ok.window_seconds == WINDOW_SECONDS
    assert abs(ok.availability - 0.9995) < 1e-9
    assert ok.freeze_release is False
    burned = snapshot(plane="admin", good=9900, total=10000)
    assert burned.target == 0.995
    assert burned.remaining_ratio < 0.20
    assert burned.freeze_release is True


def test_five_alerts_fire_on_threshold() -> None:
    assert evaluate_alert("upstream_slow", {"p95_seconds": 2.1}).firing is True
    assert evaluate_alert("upstream_slow", {"p95_seconds": 0.4}).firing is False
    assert evaluate_alert("no_candidate", {"count": 1}).firing is True
    assert evaluate_alert("event_backlog", {"depth": 1001}).firing is True
    assert evaluate_alert("unresolved_spike", {"delta": 11}).firing is True
    assert evaluate_alert("connection_unhealthy", {"unhealthy": 1}).firing is True
    fired = evaluate_alert("upstream_slow", {"p95_seconds": 3})
    assert fired.runbook.endswith("slo-alerts.md")
    assert fired.owner
    assert fired.escalation
    assert fired.dashboard
    assert fired.impact


def test_redaction_zero_hits_and_cardinality_guard() -> None:
    blob = json.dumps(
        {
            "request_id": "rid-1",
            "headers": {"authorization": "[redacted]"},
            "exemplar": {"trace": "ok"},
        }
    )
    assert scan_secrets(blob) == []
    poison = "token=sk-live-secret api_key=x password=p"
    assert scan_secrets(poison)
    assert "sk-live" not in redact("token=sk-live")
    assert allow_labels({"protocol": "openai", "status": "200"}) is True
    for name in FORBIDDEN:
        assert allow_labels({name: "x"}) is False


def test_slo_http_requires_alert_read() -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.unit.test_ops_http import _client

    anon = TestClient(app)
    denied = anon.get("/admin/v1/slo")
    assert denied.status_code == 401
    client, _token_value = _client("pricing", readonly=True)
    try:
        page = client.get("/admin/v1/slo")
        assert page.status_code == 200, page.text
        data = page.json()["data"]
        assert "dataplane" in data
        assert "admin" in data
        hops = client.get("/admin/v1/slo/traces/rid-none")
        assert hops.status_code == 200
        ev = client.post(
            "/admin/v1/slo/alerts/evaluate",
            json={"kind": "upstream_slow", "sample": {"p95_seconds": 3}},
        )
        assert ev.status_code == 200
        assert ev.json()["data"]["firing"] is True
    finally:
        client.__exit__(None, None, None)


def test_unknown_alert_kind_rejected() -> None:
    with pytest.raises(AdminError):
        evaluate_alert("sql_editor", {"count": 1})
