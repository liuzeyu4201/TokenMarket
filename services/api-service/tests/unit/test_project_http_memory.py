"""HTTP Project surface with actor override (no live SMS)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.projects.service import ProjectService
from app.domain.projects.store import MemoryProjectStore
from app.main import app


def _client(
    role: str = "buyer", workspace: str = "buyer"
) -> tuple[TestClient, uuid.UUID, MemoryProjectStore]:
    user = uuid.uuid4()
    store = MemoryProjectStore()
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role=role, status="active", workspace=workspace
    )
    client.app.state.project_service = ProjectService(store=store)
    return client, user, store


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def test_create_shared_patch_mode_rejected() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "P1",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()["data"]
        assert body["mode"] == "shared"
        assert body["status"] == "draft"
        pid = body["project_id"]
        patched = client.patch(
            f"/api/v1/projects/{pid}",
            json={"display_name": "P1", "mode": "dedicated"},
        )
        assert patched.status_code == 400
        assert patched.json()["code"] == "MODE_IMMUTABLE"
        got = client.get(f"/api/v1/projects/{pid}")
        assert got.json()["data"]["mode"] == "shared"
    finally:
        _close(client)


def test_create_dedicated_and_list() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Excl",
                "mode": "dedicated",
                "enabled_protocols": ["anthropic", "vertex"],
            },
        )
        assert created.status_code == 201
        listed = client.get("/api/v1/projects")
        assert listed.status_code == 200
        items = listed.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["mode"] == "dedicated"
    finally:
        _close(client)


def test_name_conflict() -> None:
    client, _, _ = _client()
    try:
        body = {
            "display_name": "Dup",
            "mode": "shared",
            "enabled_protocols": ["openai"],
        }
        assert client.post("/api/v1/projects", json=body).status_code == 201
        dup = client.post("/api/v1/projects", json={**body, "display_name": "dup"})
        assert dup.status_code == 409
        assert dup.json()["code"] == "NAME_CONFLICT"
    finally:
        _close(client)


def test_archive_admission_and_enable_fail_closed() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Life",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        pid = created.json()["data"]["project_id"]
        assert client.post(f"/api/v1/projects/{pid}/activate").status_code == 200
        enable = client.post(f"/api/v1/projects/{pid}/protocols/anthropic/enable")
        assert enable.status_code == 409
        assert enable.json()["code"] == "PROVIDER_BINDING_REQUIRED"
        archived = client.post(f"/api/v1/projects/{pid}/archive")
        assert archived.status_code == 200
        adm = client.get(f"/api/v1/projects/{pid}/admission")
        assert adm.status_code == 200
        assert adm.json()["data"]["allows_new_proxy"] is False
    finally:
        _close(client)


def test_delete_blocked() -> None:
    client, _, store = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Blk",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        pid = created.json()["data"]["project_id"]
        store.add_blocker(uuid.UUID(pid), "unsettled_ledger", "led-1")
        deleted = client.delete(f"/api/v1/projects/{pid}")
        assert deleted.status_code == 409
        assert deleted.json()["code"] == "DELETE_BLOCKED"
        assert deleted.json()["data"]["blockers"][0]["kind"] == "unsettled_ledger"
    finally:
        _close(client)


def test_idor_shape() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "A",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        pid = created.json()["data"]["project_id"]
        client.app.state.actor_override = Actor(
            user_id=uuid.uuid4(),
            role="buyer",
            status="active",
            workspace="buyer",
        )
        foreign = client.get(f"/api/v1/projects/{pid}")
        missing = client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert missing.status_code == foreign.status_code == 404
        assert missing.json()["code"] == foreign.json()["code"] == "NOT_FOUND"
        assert missing.json()["message"] == foreign.json()["message"]
    finally:
        _close(client)


def test_seller_workspace_403() -> None:
    client, _, _ = _client(role="both", workspace="seller")
    try:
        res = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Nope",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        assert res.status_code == 403
        assert res.json()["code"] == "FORBIDDEN_ROLE"
    finally:
        _close(client)


def test_rename_disable_and_delete() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "Old",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        pid = created.json()["data"]["project_id"]
        renamed = client.patch(f"/api/v1/projects/{pid}", json={"display_name": "New"})
        assert renamed.status_code == 200
        assert renamed.json()["data"]["display_name"] == "New"
        disabled = client.post(f"/api/v1/projects/{pid}/protocols/openai/disable")
        assert disabled.status_code == 200
        assert disabled.json()["data"]["enabled_protocols"] == []
        deleted = client.delete(f"/api/v1/projects/{pid}")
        assert deleted.status_code == 200
        assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    finally:
        _close(client)


def test_illegal_transition() -> None:
    client, _, _ = _client()
    try:
        created = client.post(
            "/api/v1/projects",
            json={
                "display_name": "DraftOnly",
                "mode": "shared",
                "enabled_protocols": ["openai"],
            },
        )
        pid = created.json()["data"]["project_id"]
        suspended = client.post(f"/api/v1/projects/{pid}/suspend")
        assert suspended.status_code == 409
        assert suspended.json()["code"] == "ILLEGAL_STATE_TRANSITION"
        got = client.get(f"/api/v1/projects/{pid}")
        assert got.json()["data"]["status"] == "draft"
    finally:
        _close(client)
