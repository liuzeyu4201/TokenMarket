"""HTTP Binding surface with actor override."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.bindings.ports import (
    AlwaysPriceLookup,
    ConnectionFact,
    DictConnectionLookup,
)
from app.domain.bindings.service import BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.main import app


def _client():
    user = uuid.uuid4()
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    bind = BindingService(store=bindings, projects=projects, prices=AlwaysPriceLookup())
    proj = ProjectService(store=projects, binding=bind)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="buyer", status="active", workspace="buyer"
    )
    client.app.state.project_service = proj
    client.app.state.binding_service = bind
    return client, user, proj


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _project(client: TestClient) -> str:
    res = client.post(
        "/api/v1/projects",
        json={
            "display_name": "BindP",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["project_id"]


def test_create_publish_sdk_hint_and_admit() -> None:
    client, _, _ = _client()
    try:
        pid = _project(client)
        created = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "shared",
                "allowed_models": ["gpt-test"],
            },
        )
        assert created.status_code == 201, created.text
        bid = created.json()["data"]["binding_id"]
        published = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/publish")
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "active"
        hint = client.get(f"/api/v1/projects/{pid}/bindings/{bid}/sdk-hint")
        assert hint.status_code == 200
        data = hint.json()["data"]
        assert "secret" not in data
        assert "api_key" not in data
        assert data["protocol"] == "openai"
        admit = client.post(
            f"/api/v1/projects/{pid}/bindings/admit",
            json={"protocol": "openai", "provider": "openai", "model": "gpt-test"},
        )
        assert admit.status_code == 200
        cross = client.post(
            f"/api/v1/projects/{pid}/bindings/admit",
            json={"protocol": "openai", "provider": "vertex", "model": "gpt-test"},
        )
        assert cross.status_code == 409
        assert cross.json()["code"] == "PROTOCOL_MISMATCH"
        enable = client.post(f"/api/v1/projects/{pid}/protocols/openai/enable")
        # already enabled at create
        assert enable.status_code in (200, 409)
        enable_a = client.post(f"/api/v1/projects/{pid}/protocols/anthropic/enable")
        assert enable_a.status_code == 409
        assert enable_a.json()["code"] == "PROVIDER_BINDING_REQUIRED"
    finally:
        _close(client)


def test_mode_mismatch_http() -> None:
    client, _, _ = _client()
    try:
        pid = _project(client)
        res = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "dedicated",
                "connection_id": str(uuid.uuid4()),
            },
        )
        assert res.status_code == 409
        assert res.json()["code"] == "MODE_MISMATCH"
    finally:
        _close(client)


def test_list_get_validate_deactivate_and_degrade() -> None:
    client, _, _ = _client()
    try:
        pid = _project(client)
        created = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "shared",
                "allowed_models": ["gpt-test"],
            },
        )
        bid = created.json()["data"]["binding_id"]
        listed = client.get(f"/api/v1/projects/{pid}/bindings")
        assert listed.status_code == 200
        assert len(listed.json()["data"]["items"]) == 1
        got = client.get(f"/api/v1/projects/{pid}/bindings/{bid}")
        assert got.status_code == 200
        validated = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/validate")
        assert validated.status_code == 200
        assert validated.json()["data"]["status"] == "validated"
        published = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/publish")
        assert published.status_code == 200
        active = client.get(f"/api/v1/projects/{pid}/bindings/active/openai")
        assert active.status_code == 200
        stopped = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/deactivate")
        assert stopped.status_code == 200
        assert stopped.json()["data"]["status"] == "inactive"
        client.app.state.internal_token = "itok"
        deg = client.post(
            "/internal/v1/bindings/degrade",
            json={"connection_id": str(uuid.uuid4())},
            headers={"X-Internal-Token": "itok"},
        )
        assert deg.status_code == 200
        denied = client.post(
            "/internal/v1/bindings/degrade",
            json={"connection_id": str(uuid.uuid4())},
        )
        assert denied.status_code == 401
    finally:
        _close(client)


def test_replace_preview_and_unconfirmed_http() -> None:
    user = uuid.uuid4()
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    conns = DictConnectionLookup()
    cid = uuid.uuid4()
    conns.put(
        ConnectionFact(
            connection_id=cid,
            provider="openai",
            supply_mode="dedicated",
            usable=True,
        )
    )
    bind = BindingService(
        store=bindings, projects=projects, prices=AlwaysPriceLookup(), connections=conns
    )
    proj = ProjectService(store=projects, binding=bind)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="buyer", status="active", workspace="buyer"
    )
    client.app.state.project_service = proj
    client.app.state.binding_service = bind
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Ded",
                "mode": "dedicated",
                "enabled_protocols": ["openai"],
            },
        )
        assert created.status_code == 201, created.text
        pid = created.json()["data"]["project_id"]
        binding = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "dedicated",
                "connection_id": str(cid),
            },
        )
        assert binding.status_code == 201, binding.text
        bid = binding.json()["data"]["binding_id"]
        published = client.post(f"/api/v1/projects/{pid}/bindings/{bid}/publish")
        assert published.status_code == 200, published.text
        preview = client.get(f"/api/v1/projects/{pid}/bindings/{bid}/replace-preview")
        assert preview.status_code == 200, preview.text
        body = preview.json()["data"]
        assert body["migrates"] is False
        assert "files" in body["non_migrating"]
        denied = client.post(
            f"/api/v1/projects/{pid}/bindings/{bid}/replace",
            json={
                "new_connection_id": str(uuid.uuid4()),
                "buyer_confirmed": False,
                "reason": "outage",
                "step_up": True,
            },
        )
        assert denied.status_code == 409
        assert denied.json()["code"] == "BUYER_CONFIRMATION_REQUIRED"
    finally:
        _close(client)


def test_seller_workspace_403() -> None:
    client, _, _ = _client()
    try:
        pid = _project(client)
        client.app.state.actor_override = Actor(
            user_id=client.app.state.actor_override.user_id,
            role="both",
            status="active",
            workspace="seller",
        )
        res = client.post(
            f"/api/v1/projects/{pid}/bindings",
            json={
                "protocol": "openai",
                "supply_mode": "shared",
                "allowed_models": ["m"],
            },
        )
        assert res.status_code == 403
    finally:
        _close(client)
