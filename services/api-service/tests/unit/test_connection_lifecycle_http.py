"""HTTP supply lifecycle."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.connections.health import HealthService, ProbeOutcome, ScriptedProbe
from app.domain.connections.lifecycle import LifecycleService, ScriptedDependencies
from app.domain.connections.service import ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.main import app

SECRET = "sk-http-life-ok"
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


def _client():
    user = uuid.uuid4()
    store = MemoryConnectionStore()
    conn = ConnectionService(
        CredentialEncryptor(b"k" * 32, "v1"),
        b"f" * 32,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    probe = ScriptedProbe()
    probe.by_secret[SECRET] = ProbeOutcome(
        "ok", [{"path_template": "/v1/chat/completions"}]
    )
    health = HealthService(conn, probe, catalog=CATALOG)
    life = LifecycleService(conn, dependencies=ScriptedDependencies())
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="both", status="active", workspace="seller"
    )
    client.app.state.connection_service = conn
    client.app.state.health_service = health
    client.app.state.lifecycle_service = life
    client.app.state.internal_token = "itok"
    return client, user


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _listed(client: TestClient) -> str:
    created = client.post(
        "/api/v1/provider-connections",
        json={
            "provider": "openai",
            "supply_mode": "shared",
            "credential": {"secret": SECRET},
        },
    )
    assert created.status_code == 201, created.text
    cid = created.json()["data"]["connection_id"]
    listed = client.post(f"/api/v1/provider-connections/{cid}/list")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["lifecycle_state"] == "listed"
    return cid


def test_list_pause_routable_and_mode_lock() -> None:
    client, _ = _client()
    try:
        cid = _listed(client)
        locked = client.patch(
            f"/api/v1/provider-connections/{cid}/supply-mode",
            json={"supply_mode": "dedicated"},
        )
        assert locked.status_code == 409
        assert locked.json()["code"] == "MODE_LOCKED"
        paused = client.post(f"/api/v1/provider-connections/{cid}/pause")
        assert paused.status_code == 200
        assert paused.json()["data"]["lifecycle_state"] == "paused"
        pool = client.get(
            "/internal/v1/provider-connections/routable?supply_mode=shared",
            headers={"X-Internal-Token": "itok"},
        )
        assert pool.status_code == 200
        ids = [i["connection_id"] for i in pool.json()["data"]["items"]]
        assert cid not in ids
        health = client.get(f"/api/v1/provider-connections/{cid}/health")
        assert health.json()["data"]["admits_new"] is False
    finally:
        _close(client)


def test_delete_listed_blocked() -> None:
    client, _ = _client()
    try:
        cid = _listed(client)
        deleted = client.delete(f"/api/v1/provider-connections/{cid}")
        assert deleted.status_code == 409
    finally:
        _close(client)
