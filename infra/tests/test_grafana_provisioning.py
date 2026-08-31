"""Versioned Grafana dashboard/alert provisioning (SF19)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH_DIR = REPO / "infra" / "grafana" / "provisioning" / "dashboards"
DS = REPO / "infra" / "grafana" / "provisioning" / "datasources" / "prometheus.yaml"


def test_dashboard_json_valid_and_six_core_panels() -> None:
    path = DASH_DIR / "v01-proxy-overview.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["uid"] == "tokenmarket-v01-proxy"
    assert data["refresh"] == "10s"
    titles = {p["title"] for p in data["panels"]}
    for need in (
        "QPS",
        "P95 latency",
        "4xx client error ratio",
        "5xx / upstream system error ratio",
        "Key inventory",
        "Health checks",
        "Usage persist",
    ):
        assert need in titles
    for panel in data["panels"]:
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue")
        assert no_value, panel["title"]
        blob = json.dumps(panel)
        assert "request_id" not in blob
        assert "api_key" not in blob


def test_v02_slo_dashboard_panels() -> None:
    path = DASH_DIR / "v02-slo-overview.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["uid"] == "tokenmarket-v02-slo"
    titles = {p["title"] for p in data["panels"]}
    for need in (
        "Dataplane availability",
        "Admin availability",
        "Dataplane error budget remaining",
        "Platform vs upstream latency",
        "SSE first event",
    ):
        assert need in titles
    blob = json.dumps(data)
    assert "request_id" not in blob
    assert "api_key" not in blob


def test_datasource_and_provider_files() -> None:
    assert DS.is_file()
    text = DS.read_text(encoding="utf-8")
    assert "prometheus" in text
    assert "host.docker.internal:9090" in text
    assert "127.0.0.1:9090" not in text
    provider = (DASH_DIR / "dashboards.yaml").read_text(encoding="utf-8")
    assert "updateIntervalSeconds: 10" in provider


def test_compose_files_mount_provisioning() -> None:
    local = (REPO / "infra" / "docker" / "compose.local.yml").read_text(
        encoding="utf-8"
    )
    middleware = (REPO / "infra" / "docker" / "compose.middleware.yml").read_text(
        encoding="utf-8"
    )
    assert "GF_PATHS_PROVISIONING: /etc/grafana/provisioning" in local
    assert "./grafana-provisioning" in local
    assert "host.docker.internal:host-gateway" in local
    assert "GF_PATHS_PROVISIONING: /etc/grafana/provisioning" in middleware
    assert "../grafana/provisioning" in middleware
