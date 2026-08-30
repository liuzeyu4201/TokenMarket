"""HTTP Project proxy keys."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.bindings.ports import AlwaysPriceLookup
from app.domain.bindings.service import BindingService
from app.domain.bindings.store import MemoryBindingStore
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.domain.proxykeys.service import ProxyKeyService
from app.main import app


def _client():
    user = uuid.uuid4()
    projects = MemoryProjectStore()
    bindings = MemoryBindingStore()
    bind = BindingService(store=bindings, projects=projects, prices=AlwaysPriceLookup())
    proj = ProjectService(store=projects, binding=bind)
    keys = ProxyKeyService(b"p" * 32, projects=projects, bindings=bind)
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role="buyer", status="active", workspace="buyer"
    )
    client.app.state.project_service = proj
    client.app.state.binding_service = bind
    client.app.state.proxy_key_service = keys
    return client, user, proj, bind


def _close(c: TestClient) -> None:
    c.__exit__(None, None, None)


def _project_with_binding(client: TestClient) -> str:
    created = client.post(
        "/api/v1/projects",
        json={
            "display_name": "Keys",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        },
    )
    pid = created.json()["data"]["project_id"]
    draft = client.post(
        f"/api/v1/projects/{pid}/bindings",
        json={
            "protocol": "openai",
            "supply_mode": "shared",
            "allowed_models": ["gpt-test"],
        },
    )
    bid = draft.json()["data"]["binding_id"]
    client.post(f"/api/v1/projects/{pid}/bindings/{bid}/publish")
    return pid


def test_issue_list_no_secret_and_revoke() -> None:
    client, _, _, _ = _client()
    try:
        pid = _project_with_binding(client)
        issued = client.post(
            f"/api/v1/projects/{pid}/proxy-keys",
            json={"protocols": ["openai"], "allowed_models": ["gpt-test"], "name": "n"},
        )
        assert issued.status_code == 201, issued.text
        secret = issued.json()["data"]["secret"]
        assert secret.startswith("tmk-")
        listed = client.get(f"/api/v1/projects/{pid}/proxy-keys")
        assert listed.status_code == 200
        item = listed.json()["data"]["items"][0]
        assert "secret" not in item
        assert secret not in listed.text
        kid = item["key_id"]
        revoked = client.post(f"/api/v1/projects/{pid}/proxy-keys/{kid}/revoke")
        assert revoked.status_code == 200
        assert revoked.json()["data"]["status"] == "revoked"
        foreign = client.post(
            f"/api/v1/projects/{uuid.uuid4()}/proxy-keys/{kid}/revoke"
        )
        assert foreign.status_code == 404
        issued2 = client.post(
            f"/api/v1/projects/{pid}/proxy-keys",
            json={"protocols": ["openai"], "allowed_models": ["gpt-test"], "name": "n2"},
        )
        kid2 = issued2.json()["data"]["key_id"]
        assert (
            client.post(f"/api/v1/projects/{pid}/proxy-keys/{kid2}/disable").status_code
            == 200
        )
        enabled = client.post(f"/api/v1/projects/{pid}/proxy-keys/{kid2}/enable")
        assert enabled.status_code == 200
        rotated = client.post(f"/api/v1/projects/{pid}/proxy-keys/{kid2}/rotate")
        assert rotated.status_code == 200
        assert rotated.json()["data"]["secret"].startswith("tmk-")
    finally:
        _close(client)
