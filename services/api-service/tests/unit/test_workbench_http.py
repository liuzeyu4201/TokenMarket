from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.connections.health import HealthService, ProbeOutcome, ScriptedProbe
from app.domain.connections.lifecycle import LifecycleService, ScriptedDependencies
from app.domain.connections.service import ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.workbench.service import WorkbenchService
from app.main import app

SECRET = "sk-wb-ok"
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
    client.app.state.workbench_service = WorkbenchService()
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
    return cid


def test_quote_and_capacity_http() -> None:
    client, _ = _client()
    try:
        cid = _listed(client)
        ok = client.post(
            f"/api/v1/seller/workbench/{cid}/quotes",
            json={"multiplier_bps": 10000},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["seq"] == 1
        bad = client.post(
            f"/api/v1/seller/workbench/{cid}/quotes",
            json={"multiplier_bps": 1000},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "QUOTE_OUT_OF_BOUNDS"
        cap = client.post(
            f"/api/v1/seller/workbench/{cid}/capacity",
            json={"declared_capacity": 0},
        )
        assert cap.status_code == 200
        listing = client.get("/api/v1/seller/workbench")
        assert listing.status_code == 200, listing.text
        card = listing.json()["data"]["items"][0]
        assert card["admits_new"] is False
        assert "buyer_multiplier" not in str(card).lower()
        assert card["earnings"]["settled_minor"] == 0
    finally:
        _close(client)


def test_buyer_workspace_forbidden() -> None:
    client, user = _client()
    try:
        client.app.state.actor_override = Actor(
            user_id=user, role="both", status="active", workspace="buyer"
        )
        resp = client.get("/api/v1/seller/workbench")
        assert resp.status_code == 403
    finally:
        _close(client)
