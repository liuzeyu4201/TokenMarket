"""HTTP verify/health/capabilities without plaintext."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.connections.health import HealthService, ProbeOutcome, ScriptedProbe
from app.domain.connections.service import ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.main import app

SECRET = "sk-http-verify-never-echo"

CATALOG = {
    "catalog_major": 1,
    "records": [
        {
            "provider": "openai",
            "stability": "stable",
            "path_template": "/v1/chat/completions",
            "capability_tags": [],
        }
    ],
}


def _enc() -> CredentialEncryptor:
    return CredentialEncryptor(b"k" * 32, "v1")


def _client(workspace: str = "seller", role: str = "both"):
    user = uuid.uuid4()
    store = MemoryConnectionStore()
    conn = ConnectionService(
        _enc(),
        b"f" * 32,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    probe = ScriptedProbe()
    probe.by_secret[SECRET] = ProbeOutcome(
        "ok",
        [{"path_template": "/v1/chat/completions", "model": "gpt-test"}],
        redacted_detail=f"upstream said {SECRET}",
    )
    health = HealthService(conn, probe, catalog=CATALOG)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role=role, status="active", workspace=workspace
    )
    client.app.state.connection_service = conn
    client.app.state.health_service = health
    client.app.state.internal_token = "itok"
    return client, user, probe


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _create(client: TestClient) -> str:
    res = client.post(
        "/api/v1/provider-connections",
        json={
            "provider": "openai",
            "supply_mode": "shared",
            "credential": {"secret": SECRET},
        },
    )
    assert res.status_code == 201, res.text
    blob = json.dumps(res.json())
    assert SECRET not in blob
    return res.json()["data"]["connection_id"]


def test_verify_ok_and_no_secret() -> None:
    client, _, _ = _client()
    try:
        cid = _create(client)
        res = client.post(f"/api/v1/provider-connections/{cid}/verify")
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["category"] == "ok"
        assert data["health_state"] == "healthy"
        assert SECRET not in json.dumps(res.json())
        assert data["capabilities"]
        health = client.get(f"/api/v1/provider-connections/{cid}/health")
        assert health.status_code == 200
        assert health.json()["data"]["routable"] is True
        caps = client.get(f"/api/v1/provider-connections/{cid}/capabilities")
        assert caps.status_code == 200
        assert len(caps.json()["data"]["items"]) >= 1
        internal = client.get(
            f"/internal/v1/provider-connections/{cid}/health",
            headers={"X-Internal-Token": "itok"},
        )
        assert internal.status_code == 200
        assert "secret" not in json.dumps(internal.json())
        denied = client.get(f"/internal/v1/provider-connections/{cid}/health")
        assert denied.status_code == 401
    finally:
        _close(client)


def test_verify_buyer_403() -> None:
    client, user, _ = _client(workspace="seller", role="both")
    try:
        cid = _create(client)
        client.app.state.actor_override = Actor(
            user_id=user, role="both", status="active", workspace="buyer"
        )
        res = client.post(f"/api/v1/provider-connections/{cid}/verify")
        assert res.status_code == 403
        assert res.json()["code"] == "FORBIDDEN_ROLE"
    finally:
        _close(client)


def test_invalid_credential_category() -> None:
    client, _, probe = _client()
    try:
        cid = _create(client)
        probe.by_secret[SECRET] = ProbeOutcome("invalid_credential", [])
        res = client.post(f"/api/v1/provider-connections/{cid}/verify")
        assert res.status_code == 200
        assert res.json()["data"]["category"] == "invalid_credential"
        assert res.json()["data"]["health_state"] == "unhealthy"
        assert SECRET not in json.dumps(res.json())
    finally:
        _close(client)
