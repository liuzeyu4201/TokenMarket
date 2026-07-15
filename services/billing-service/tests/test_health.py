"""Billing service baseline health contract tests (SF01).

These tests verify the minimal operational scaffold defined in
``specs/001-repository-workflow-baseline/contracts/service-health.openapi.yaml``.
No TokenMarket business behavior is exercised.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Sync TestClient for the Billing service FastAPI app."""
    return TestClient(app)


_SERVICE = "billing-service"


def test_liveness_returns_200_with_contract_fields(client: TestClient) -> None:
    """GET /health/live returns the alive health response per the OpenAPI contract."""
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == _SERVICE
    assert payload["status"] == "alive"
    assert payload["version"]
    assert payload["request_id"]
    assert set(payload.keys()) == {"service", "status", "version", "request_id"}


def test_readiness_returns_200_without_sf02_dependencies(client: TestClient) -> None:
    """GET /health/ready succeeds without probing PostgreSQL/Redis/Kafka/SF02."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == _SERVICE
    assert payload["status"] == "ready"
    assert payload["version"]
    assert payload["request_id"]
    assert set(payload.keys()) == {"service", "status", "version", "request_id"}


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    """GET /metrics returns Prometheus-compatible text without secrets."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert _SERVICE in body or "service" in body
    # No credential-like patterns should appear in metrics output.
    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    assert "token" not in body.lower()


def test_request_id_is_propagated(client: TestClient) -> None:
    """A provided X-Request-Id header is echoed in the health response."""
    request_id = "billing-test-req-42"
    response = client.get("/health/live", headers={"X-Request-Id": request_id})
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id


def test_unknown_business_path_returns_404(client: TestClient) -> None:
    """Routes outside the operational contract return 404, not 500."""
    response = client.get("/api/v1/billing/nonexistent")
    assert response.status_code == 404
