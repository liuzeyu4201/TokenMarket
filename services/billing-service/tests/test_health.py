"""Billing service health contract tests (SF01 liveness + SF02 readiness).

Liveness, request-id, and 404 behavior remain the unchanged SF01 scaffold.
Readiness follows health contract v1.1: a fresh, bounded PostgreSQL probe per
request. Success keeps the exact SF01 200 shape; failure returns the
contracted 503 dependency shape naming only ``postgres`` with a stable safe
code (``INVALID_CONFIG`` or ``DEPENDENCY_NOT_READY``).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import ProbeErrorCategory, ProbeOutcome
from app.main import app

_SERVICE = "billing-service"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Sync TestClient (no lifespan needed for liveness/metrics/404)."""
    return TestClient(app)


def test_liveness_returns_200_with_contract_fields(client: TestClient) -> None:
    """GET /health/live returns the alive health response per the contract."""
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == _SERVICE
    assert payload["status"] == "alive"
    assert payload["version"]
    assert payload["request_id"]
    assert set(payload.keys()) == {"service", "status", "version", "request_id"}


def test_liveness_never_probes_postgres(readiness_client, make_probe) -> None:
    """Liveness stays 200 and independent while the dependency probe fails."""
    probe = make_probe(
        [ProbeOutcome(ok=False, category=ProbeErrorCategory.UNAVAILABLE)]
    )
    with readiness_client(probe) as live_client:
        response = live_client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "alive"
    assert set(payload.keys()) == {"service", "status", "version", "request_id"}
    assert probe.calls == 0


def test_readiness_200_shape_is_unchanged(readiness_client, make_probe) -> None:
    """A successful probe returns the exact SF01 readiness shape once."""
    probe = make_probe()
    with readiness_client(probe) as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == _SERVICE
    assert payload["status"] == "ready"
    assert payload["version"]
    assert payload["request_id"]
    assert set(payload.keys()) == {"service", "status", "version", "request_id"}
    assert probe.calls == 1


@pytest.mark.parametrize(
    "category",
    [
        ProbeErrorCategory.AUTH,
        ProbeErrorCategory.QUERY,
        ProbeErrorCategory.TIMEOUT,
        ProbeErrorCategory.UNAVAILABLE,
    ],
)
def test_readiness_503_safe_shape_for_dependency_failures(
    readiness_client, make_probe, category: ProbeErrorCategory
) -> None:
    """Auth/query/timeout/unavailable map to the contracted safe 503 shape."""
    probe = make_probe([ProbeOutcome(ok=False, category=category)])
    with readiness_client(probe) as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["service"] == _SERVICE
    assert payload["status"] == "not_ready"
    assert payload["version"]
    assert payload["request_id"]
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]
    assert set(payload.keys()) == {
        "service",
        "status",
        "version",
        "request_id",
        "dependencies",
    }
    assert set(payload["dependencies"][0].keys()) == {"name", "status", "code"}


def test_readiness_503_invalid_config_shape(readiness_client, make_probe) -> None:
    """An invalid-config probe result maps to the INVALID_CONFIG code."""
    probe = make_probe(
        [ProbeOutcome(ok=False, category=ProbeErrorCategory.INVALID_CONFIG)]
    )
    with readiness_client(probe) as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "INVALID_CONFIG"}
    ]


def test_readiness_without_database_url_is_invalid_config(
    readiness_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing DATABASE_URL fails closed with INVALID_CONFIG, liveness aside."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with readiness_client() as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "INVALID_CONFIG"}
    ]


def test_readiness_with_bad_database_url_never_echoes_it(
    readiness_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsupported-driver config yields INVALID_CONFIG with zero URL leakage."""
    canary = "tm_local_canarysecretvalue123"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg2://user:{canary}@127.0.0.1:5544/db",
    )
    with readiness_client() as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["dependencies"][0]["code"] == "INVALID_CONFIG"
    assert canary not in response.text
    assert "psycopg2" not in response.text
    assert "127.0.0.1" not in response.text


def test_raising_probe_maps_to_safe_503(readiness_client) -> None:
    """A crashing probe can never leak exception bodies or return 500."""

    async def _boom() -> ProbeOutcome:
        raise RuntimeError("tm_local_should_never_surface")

    with readiness_client(_boom) as ready_client:
        response = ready_client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]
    assert "tm_local_should_never_surface" not in response.text
    assert "RuntimeError" not in response.text


def test_request_id_preserved_on_503(readiness_client, make_probe) -> None:
    """The correlation ID is echoed in the 503 body and response header."""
    probe = make_probe([ProbeOutcome(ok=False, category=ProbeErrorCategory.AUTH)])
    with readiness_client(probe) as ready_client:
        response = ready_client.get(
            "/health/ready", headers={"X-Request-Id": "billing-req-503"}
        )
    assert response.status_code == 503
    assert response.json()["request_id"] == "billing-req-503"
    assert response.headers["X-Request-ID"] == "billing-req-503"


def test_readiness_recovers_without_service_restart(
    readiness_client, make_probe
) -> None:
    """A fresh probe per request recovers 503 -> 200 with no restart."""
    probe = make_probe(
        [ProbeOutcome(ok=False, category=ProbeErrorCategory.UNAVAILABLE)]
    )
    with readiness_client(probe) as ready_client:
        first = ready_client.get("/health/ready")
        second = ready_client.get("/health/ready")
    assert first.status_code == 503
    assert first.json()["status"] == "not_ready"
    assert second.status_code == 200
    assert second.json()["status"] == "ready"
    assert set(second.json().keys()) == {
        "service",
        "status",
        "version",
        "request_id",
    }
    assert probe.calls == 2


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    """GET /metrics returns Prometheus text without secrets or URLs."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert _SERVICE in body or "service" in body
    lowered = body.lower()
    # Credential/URL material must never appear. The repository-mandated
    # ``tokenmarket_`` metric prefix is not a credential pattern.
    assert "password" not in lowered
    assert "secret" not in lowered
    assert "tm_local_" not in lowered
    assert "postgresql://" not in lowered
    assert "://" not in body


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
