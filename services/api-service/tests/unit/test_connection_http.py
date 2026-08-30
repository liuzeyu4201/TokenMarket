"""HTTP Provider Connection surface: no plaintext read-back."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.connections.service import ConnectionService
from app.domain.connections.store import MemoryConnectionStore
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.main import app

SECRET = "sk-http-plaintext-must-not-echo"


def _enc() -> CredentialEncryptor:
    return CredentialEncryptor(b"k" * 32, "v1")


def _client(workspace: str = "seller", role: str = "both"):
    user = uuid.uuid4()
    store = MemoryConnectionStore()
    svc = ConnectionService(
        _enc(),
        b"f" * 32,
        store=store,
        resolver=lambda _h, _p: ["1.1.1.1"],
    )
    client = TestClient(app)
    client.__enter__()
    client.app.state.actor_override = Actor(
        user_id=user, role=role, status="active", workspace=workspace
    )
    client.app.state.connection_service = svc
    client.app.state.internal_token = "itok"
    return client, user, svc, store


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _body(**kwargs):
    payload = {
        "provider": kwargs.get("provider", "openai"),
        "supply_mode": kwargs.get("supply_mode", "shared"),
        "credential": {"secret": kwargs.get("secret", SECRET)},
    }
    if "base_url" in kwargs:
        payload["base_url"] = kwargs["base_url"]
    if kwargs.get("project_number"):
        payload["credential"]["project_number"] = kwargs["project_number"]
    if kwargs.get("location"):
        payload["credential"]["location"] = kwargs["location"]
    return payload


_FORBIDDEN_KEYS = frozenset(
    {"ciphertext", "nonce", "tag", "plaintext", "api_key", "credential", "secret"}
)


def _assert_public(obj: object, secret: str = SECRET) -> None:
    blob = json.dumps(obj)
    assert secret not in blob
    assert "ciphertext" not in blob.lower()
    assert "plaintext" not in blob.lower()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                assert key not in _FORBIDDEN_KEYS
                walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            assert secret not in node

    walk(obj)


def test_create_list_get_have_no_secret() -> None:
    client, _, _, store = _client()
    try:
        created = client.post("/api/v1/provider-connections", json=_body())
        assert created.status_code == 201, created.text
        data = created.json()["data"]
        _assert_public(created.json())
        assert data["credential_fingerprint"]
        assert data["credential_version"] == 1
        cid = data["connection_id"]
        listed = client.get("/api/v1/provider-connections")
        assert listed.status_code == 200
        _assert_public(listed.json())
        assert len(listed.json()["data"]["items"]) == 1
        got = client.get(f"/api/v1/provider-connections/{cid}")
        assert got.status_code == 200
        _assert_public(got.json())
        assert SECRET not in json.dumps(store.audits, default=str)
        stored = store.get(uuid.UUID(cid))
        assert stored is not None
        assert stored.ciphertext != SECRET.encode("utf-8")
    finally:
        _close(client)


def test_buyer_workspace_403() -> None:
    client, _, _, _ = _client(workspace="buyer", role="both")
    try:
        res = client.post("/api/v1/provider-connections", json=_body())
        assert res.status_code == 403
        assert res.json()["code"] == "FORBIDDEN_ROLE"
        _assert_public(res.json())
        listed = client.get("/api/v1/provider-connections")
        assert listed.status_code == 403
    finally:
        _close(client)


def test_ssrf_rejected_http() -> None:
    client, _, _, _ = _client()
    try:
        res = client.post(
            "/api/v1/provider-connections",
            json=_body(base_url="https://169.254.169.254/latest/meta-data"),
        )
        assert res.status_code == 400
        assert res.json()["code"] == "SSRF_REJECTED"
        http = client.post(
            "/api/v1/provider-connections",
            json=_body(base_url="http://api.openai.com"),
        )
        assert http.status_code == 400
    finally:
        _close(client)


def test_unwrap_requires_internal_token_and_audits() -> None:
    client, _, svc, store = _client()
    try:
        created = client.post("/api/v1/provider-connections", json=_body())
        cid = created.json()["data"]["connection_id"]
        denied = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "proxy"},
        )
        assert denied.status_code == 401
        _assert_public(denied.json())
        wrong = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "proxy"},
            headers={"X-Internal-Token": "nope"},
        )
        assert wrong.status_code == 401
        bad_purpose = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "admin"},
            headers={"X-Internal-Token": "itok"},
        )
        assert bad_purpose.status_code == 400
        public_get = client.get(f"/api/v1/provider-connections/{cid}")
        _assert_public(public_get.json())
        ok = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "proxy"},
            headers={"X-Internal-Token": "itok"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["secret"] == SECRET
        assert SECRET not in json.dumps(store.audits, default=str)
        verify = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "verify"},
            headers={"X-Internal-Token": "itok"},
        )
        assert verify.status_code == 200
        assert (
            svc.unwrap(connection_id=uuid.UUID(cid), purpose="proxy", request_id="d")
            == SECRET
        )
    finally:
        _close(client)


def test_replace_cas_and_delete_wipe() -> None:
    client, _, _, store = _client()
    try:
        created = client.post("/api/v1/provider-connections", json=_body())
        cid = created.json()["data"]["connection_id"]
        conflict = client.put(
            f"/api/v1/provider-connections/{cid}/credential",
            json={"credential": {"secret": "next-one-eeeeeeee"}, "expected_version": 9},
        )
        assert conflict.status_code == 409
        replaced = client.put(
            f"/api/v1/provider-connections/{cid}/credential",
            json={"credential": {"secret": "next-one-eeeeeeee"}, "expected_version": 1},
        )
        assert replaced.status_code == 200, replaced.text
        _assert_public(replaced.json(), secret="next-one-eeeeeeee")
        assert replaced.json()["data"]["credential_version"] == 2
        fp = replaced.json()["data"]["credential_fingerprint"]
        deleted = client.delete(f"/api/v1/provider-connections/{cid}")
        assert deleted.status_code == 200
        assert deleted.json()["data"]["credential_fingerprint"] == fp
        _assert_public(deleted.json())
        stored = store.get(uuid.UUID(cid))
        assert stored is not None
        assert stored.ciphertext is None
        unwrap = client.post(
            f"/internal/v1/provider-connections/{cid}/unwrap",
            json={"purpose": "proxy"},
            headers={"X-Internal-Token": "itok"},
        )
        assert unwrap.status_code == 404
        listed = client.get("/api/v1/provider-connections")
        assert listed.json()["data"]["items"] == []
    finally:
        _close(client)


def test_idor_same_shape_404() -> None:
    client, _, _, _ = _client()
    try:
        created = client.post("/api/v1/provider-connections", json=_body())
        cid = created.json()["data"]["connection_id"]
        client.app.state.actor_override = Actor(
            user_id=uuid.uuid4(), role="seller", status="active", workspace="seller"
        )
        got = client.get(f"/api/v1/provider-connections/{cid}")
        assert got.status_code == 404
        _assert_public(got.json())
    finally:
        _close(client)


def test_missing_service_returns_503() -> None:
    client, _, _, _ = _client()
    try:
        client.app.state.connection_service = None
        res = client.get("/api/v1/provider-connections")
        assert res.status_code == 503
    finally:
        _close(client)


def test_vertex_requires_project_fields() -> None:
    client, _, _, _ = _client()
    try:
        missing = client.post(
            "/api/v1/provider-connections",
            json=_body(provider="vertex", secret="sa-json"),
        )
        assert missing.status_code == 400
        ok = client.post(
            "/api/v1/provider-connections",
            json=_body(
                provider="vertex",
                secret="sa-json",
                project_number="123456",
                location="us-central1",
            ),
        )
        assert ok.status_code == 201, ok.text
        _assert_public(ok.json(), secret="sa-json")
        assert ok.json()["data"]["provider"] == "vertex"
    finally:
        _close(client)
