"""Project preview_opt_in is stored and returned on internal by-hash / snapshot."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.bindings.models import BindingRecord, utcnow
from app.domain.bindings.ports import AlwaysPriceLookup
from app.domain.bindings.service import BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.connections.service import ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.domain.proxykeys.service import ProxyKeyService, hash_proxy_secret
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.main import app


def _client():
    user = uuid.uuid4()
    proj_store = MemoryProjectStore()
    bind_store = MemoryBindingStore()
    conn_store = MemoryConnectionStore()
    enc = CredentialEncryptor(b"k" * 32, "v1")
    conn_svc = ConnectionService(
        enc, b"f" * 32, store=conn_store, resolver=lambda _h, _p: ["1.1.1.1"]
    )
    bind_svc = BindingService(
        store=bind_store, projects=proj_store, prices=AlwaysPriceLookup()
    )
    proj_svc = ProjectService(store=proj_store, binding=bind_svc)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="buyer", status="active", workspace="buyer"
    )
    client.app.state.project_service = proj_svc
    client.app.state.binding_service = bind_svc
    client.app.state.connection_service = conn_svc
    client.app.state.proxy_key_service = ProxyKeyService(
        b"p" * 32, projects=proj_store, bindings=bind_svc
    )
    client.app.state.internal_token = "itok"
    return client, user, proj_svc, bind_store, conn_svc


def test_create_preview_opt_in_round_trips_on_by_hash() -> None:
    client, user, proj_svc, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "PreviewOn",
                "mode": "shared",
                "enabled_protocols": ["openai"],
                "preview_opt_in": True,
            },
        )
        assert created.status_code == 201, created.text
        pid = created.json()["data"]["project_id"]
        assert created.json()["data"]["preview_opt_in"] is True
        draft = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "shared",
                "allowed_models": ["gpt-test"],
            },
        )
        assert draft.status_code == 201, draft.text
        bid = draft.json()["data"]["binding_id"]
        pub = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/publish")
        assert pub.status_code == 200, pub.text
        issued = client.post(
            f"/api/v1/projects/{pid}/proxy-keys",
            json={"protocols": ["openai"]},
        )
        assert issued.status_code in (200, 201), issued.text
        secret = issued.json()["data"]["secret"]
        h = hash_proxy_secret(secret, client.app.state.proxy_key_service._pepper)
        look = client.get(
            "/internal/v1/proxy-keys/by-hash",
            params={"hash": h},
            headers={"X-Internal-Token": "itok"},
        )
        assert look.status_code == 200, look.text
        assert look.json()["data"]["project_id"] == pid
        assert look.json()["data"]["project_mode"] == "shared"
        assert look.json()["data"]["preview_opt_in"] is True
    finally:
        client.__exit__(None, None, None)


def test_route_snapshot_includes_unwrapped_connection() -> None:
    client, user, proj_svc, bind_store, conn_svc = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Snap",
                "mode": "shared",
                "enabled_protocols": ["openai"],
                "preview_opt_in": False,
            },
        )
        pid = uuid.UUID(created.json()["data"]["project_id"])
        conn = conn_svc.create(
            seller_id=user,
            provider="openai",
            supply_mode="shared",
            secret="sk-snapshot-secret",
            role="seller",
            workspace="seller",
            request_id="c1",
        )
        now = utcnow()
        bind_store.create(
            BindingRecord(
                binding_id=uuid.uuid4(),
                project_id=pid,
                owner_account_id=user,
                protocol="openai",
                supply_mode="shared",
                status="published",
                version=1,
                connection_id=conn.connection_id,
                created_at=now,
                updated_at=now,
            )
        )
        snap = client.get(
            f"/internal/v1/projects/{pid}/route-snapshot",
            headers={"X-Internal-Token": "itok"},
        )
        assert snap.status_code == 200, snap.text
        data = snap.json()["data"]
        assert data["mode"] == "shared"
        assert data["preview_opt_in"] is False
        assert data["connections"]
        assert data["connections"][0]["credential"] == "sk-snapshot-secret"
        assert data["connections"][0]["base_url"]
    finally:
        client.__exit__(None, None, None)
