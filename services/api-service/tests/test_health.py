"""Operational health contract tests for api-service.

The SF01 liveness and readiness success shapes are unchanged. SF02 adds a
service-owned, bounded PostgreSQL readiness probe: when the probe fails,
readiness returns only the contracted 503 dependency shape naming ``postgres``
with a stable safe code, and recovers to the unchanged 200 shape without a
service restart. No response ever contains a URL, username, database name,
exception body, SQL, or password.
"""

from __future__ import annotations

import pytest
from conftest import MakeClient

from app.database import ProbeErrorCategory, ProbeResult

READY_200_KEYS = {"service", "status", "version", "request_id"}
NOT_READY_503_KEYS = READY_200_KEYS | {"dependencies"}


def test_liveness_returns_api_service_alive(make_client: MakeClient) -> None:
    with make_client() as handle:
        response = handle.client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == READY_200_KEYS
    assert payload["service"] == "api-service"
    assert payload["status"] == "alive"
    assert payload["version"]
    assert payload["request_id"]


def test_liveness_never_probes_postgres(make_client: MakeClient) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.UNAVAILABLE))
        response = handle.client.get("/health/live")
        assert handle.probe.calls == 0
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_returns_unchanged_200_shape(make_client: MakeClient) -> None:
    with make_client() as handle:
        response = handle.client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == READY_200_KEYS
    assert payload["service"] == "api-service"
    assert payload["status"] == "ready"
    assert payload["version"]
    assert payload["request_id"]


def test_readiness_503_names_only_postgres_with_safe_code(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.UNAVAILABLE))
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert set(payload) == NOT_READY_503_KEYS
    assert payload["service"] == "api-service"
    assert payload["status"] == "not_ready"
    assert payload["version"]
    assert payload["request_id"]
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]


@pytest.mark.parametrize(
    "category",
    [
        ProbeErrorCategory.AUTH,
        ProbeErrorCategory.QUERY,
        ProbeErrorCategory.TIMEOUT,
        ProbeErrorCategory.UNAVAILABLE,
    ],
)
def test_readiness_dependency_failures_map_to_dependency_not_ready(
    make_client: MakeClient, category: ProbeErrorCategory
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(category))
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]


def test_readiness_invalid_config_maps_to_invalid_config_code(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(
            ProbeResult.failure(ProbeErrorCategory.INVALID_CONFIG)
        )
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "INVALID_CONFIG"}
    ]


def test_readiness_without_database_url_returns_invalid_config_503(
    make_client: MakeClient,
) -> None:
    with make_client(database_url=None, inject_probe=False) as handle:
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert set(payload) == NOT_READY_503_KEYS
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "INVALID_CONFIG"}
    ]


def test_readiness_malformed_database_url_returns_invalid_config_503(
    make_client: MakeClient,
) -> None:
    with make_client(database_url="not a url", inject_probe=False) as handle:
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "INVALID_CONFIG"}
    ]


def test_readiness_recovers_to_unchanged_200_without_service_restart(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.UNAVAILABLE))
        failing = handle.client.get("/health/ready")
        recovered = handle.client.get("/health/ready")
    assert failing.status_code == 503
    assert recovered.status_code == 200
    payload = recovered.json()
    assert set(payload) == READY_200_KEYS
    assert payload["status"] == "ready"


def test_readiness_503_body_has_no_config_or_exception_data(
    make_client: MakeClient,
) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.AUTH))
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    body = response.text.lower()
    for forbidden in (
        "postgresql",
        "asyncpg",
        "127.0.0.1",
        "select 1",
        "password",
        "tm_local_",
        "traceback",
        "exception",
    ):
        assert forbidden not in body


def test_request_id_is_propagated_when_provided(make_client: MakeClient) -> None:
    request_id = "test-req-id-001"
    with make_client() as handle:
        response = handle.client.get(
            "/health/live", headers={"X-Request-ID": request_id}
        )
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_is_generated_when_absent(make_client: MakeClient) -> None:
    with make_client() as handle:
        response = handle.client.get("/health/live")
    assert response.status_code == 200
    generated = response.json()["request_id"]
    assert generated
    assert response.headers.get("X-Request-ID") == generated


def test_request_id_is_preserved_on_ready_200(make_client: MakeClient) -> None:
    request_id = "test-req-id-ready-200"
    with make_client() as handle:
        response = handle.client.get(
            "/health/ready", headers={"X-Request-ID": request_id}
        )
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_is_preserved_on_ready_503(make_client: MakeClient) -> None:
    request_id = "test-req-id-ready-503"
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.TIMEOUT))
        response = handle.client.get(
            "/health/ready", headers={"X-Request-ID": request_id}
        )
    assert response.status_code == 503
    assert response.json()["request_id"] == request_id
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_is_generated_on_ready_503(make_client: MakeClient) -> None:
    with make_client() as handle:
        handle.probe.set_outcomes(ProbeResult.failure(ProbeErrorCategory.QUERY))
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    generated = response.json()["request_id"]
    assert generated
    assert response.headers.get("X-Request-ID") == generated


def test_metrics_returns_prometheus_text_without_secrets(
    make_client: MakeClient,
) -> None:
    # The ``tokenmarket_`` prefix is the metric namespace, not a credential;
    # secret-shaped values must still never appear.
    with make_client() as handle:
        response = handle.client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert body
    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    assert "tm_local_" not in body
    assert "postgresql://" not in body
    assert "authorization" not in body.lower()


def test_unknown_business_path_returns_404(make_client: MakeClient) -> None:
    with make_client() as handle:
        response = handle.client.get("/api/v1/widgets")
    assert response.status_code == 404


def test_probe_exception_maps_to_safe_503(make_client: MakeClient) -> None:
    class RaisingProbe:
        calls = 0

        async def __call__(self) -> ProbeResult:
            self.calls += 1
            raise RuntimeError("synthetic probe failure")

    with make_client(probe=RaisingProbe()) as handle:
        response = handle.client.get("/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]
    assert "synthetic" not in response.text
