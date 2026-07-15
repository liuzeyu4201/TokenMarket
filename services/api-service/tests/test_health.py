"""Operational health contract tests for api-service.

These tests verify the SF01 service scaffold satisfies the shared service health
contract without implementing any TokenMarket business behavior and without
depending on SF02 local dependency lifecycle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# The implementation under test is intentionally absent at this stage.
# Importing it must fail with a clear module-not-found error until T037 delivers
# the api-service scaffold.
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_liveness_returns_api_service_alive(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "api-service"
    assert payload["status"] == "alive"
    assert payload["version"]
    assert payload["request_id"]


def test_readiness_returns_api_service_ready(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "api-service"
    assert payload["status"] == "ready"
    assert payload["version"]
    assert payload["request_id"]


def test_readiness_does_not_require_sf02_dependencies(client: TestClient) -> None:
    """Readiness in SF01 must not probe PostgreSQL, Redis, Kafka or AI providers."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"


def test_metrics_returns_prometheus_text_without_secrets(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert body
    # No real secret-like values should leak into the metrics text.
    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    assert "token" not in body.lower()


def test_request_id_is_propagated_when_provided(client: TestClient) -> None:
    request_id = "test-req-id-001"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    generated = response.json()["request_id"]
    assert generated
    assert response.headers.get("X-Request-ID") == generated


def test_unknown_business_path_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/widgets")
    assert response.status_code == 404
