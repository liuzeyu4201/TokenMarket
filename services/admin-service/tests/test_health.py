"""Admin service baseline health contract tests.

These tests verify the Admin service scaffold exposes the repository health
contract without business routes, does not own migrations, and does not probe
SF02 dependencies (PostgreSQL, Redis, Kafka, AI providers) in SF01.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Make repository-wide helpers available from the service test root.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# The admin-service scaffold is implemented in T045. This import is expected to
# fail until `app/main.py`, `app/health.py`, and `app/observability.py` exist.
from app.main import app  # noqa: E402
from tests.workflow.helpers import load_json  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_component() -> dict[str, Any]:
    """Load the admin-service entry from the component manifest."""
    manifest = load_json("ops", "workflow", "components.json")
    for component in manifest["components"]:
        if component["id"] == "admin-service":
            return component
    raise AssertionError("admin-service not found in component manifest")


@pytest.fixture
def migration_owners() -> dict[str, Any]:
    """Load the migration ownership registry."""
    return load_json("ops", "migrations", "owners.json")


def _assert_health_response(response: Any, expected_status: str) -> None:
    """Shared assertions for the service health contract."""
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["service"] == "admin-service"
    assert body["status"] == expected_status
    assert body["version"]
    assert body["request_id"]
    # The response must not include unspecified fields.
    assert set(body.keys()) <= {"service", "status", "version", "request_id"}


def test_liveness_returns_alive(client: TestClient) -> None:
    response = client.get("/health/live")
    _assert_health_response(response, "alive")


def test_readiness_returns_ready_without_sf02_dependencies(client: TestClient) -> None:
    """Readiness must pass without connecting to PostgreSQL/Redis/Kafka."""
    response = client.get("/health/ready")
    _assert_health_response(response, "ready")


def test_metrics_returns_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200, response.text
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert "admin" in body.lower() or "python" in body.lower()
    # Basic guard against accidental secret leakage into metrics output.
    assert "password" not in body.lower()
    assert "secret" not in body.lower()
    assert "apikey" not in body.lower()


def test_request_id_is_propagated(client: TestClient) -> None:
    request_id = "test-request-id-admin-123"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})
    _assert_health_response(response, "alive")
    assert response.json()["request_id"] == request_id


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health/live")
    _assert_health_response(response, "alive")
    generated = response.json()["request_id"]
    assert len(generated) > 0
    # Must look like a UUID or a sufficiently unique opaque identifier.
    assert re.match(r"^[0-9a-fA-F\-]{20,}$", generated) is not None


def test_admin_service_has_no_migration_action_binding(
    admin_component: dict[str, Any],
) -> None:
    actions = {binding["action"] for binding in admin_component["actions"]}
    assert "migrate" not in actions, "admin-service must not bind the migrate action"


def test_admin_service_is_listed_as_migration_non_owner(
    migration_owners: dict[str, Any],
) -> None:
    owner_ids = {owner["component_id"] for owner in migration_owners.get("owners", [])}
    non_owners = set(migration_owners.get("non_owners", []))
    assert "admin-service" not in owner_ids
    assert "admin-service" in non_owners


def test_unknown_business_path_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/admin/nonexistent")
    assert response.status_code == 404
    # Even error responses should carry a correlation/request ID.
    assert response.headers.get("X-Request-ID") or "request_id" in response.json()
