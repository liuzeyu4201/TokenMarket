"""HTTP surface for seller/proxy keys and internal gateway APIs."""

from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.validator_port import ValidationSnapshot
from app.main import app


class FakeValidator:
    def __init__(self, snap: ValidationSnapshot) -> None:
        self.snap = snap

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        return self.snap


def test_onboard_and_internal_routable() -> None:
    user = uuid.uuid4()
    store = MemoryKeyStore()
    enc = CredentialEncryptor(os.urandom(32), "v1")
    with TestClient(app) as client:
        client.app.state.actor_override = Actor(
            user_id=user, role="seller", status="active"
        )
        client.app.state.seller_key_store = store
        client.app.state.seller_encryptor = enc
        client.app.state.seller_fp_secret = b"s" * 32
        client.app.state.seller_validator = FakeValidator(
            ValidationSnapshot(
                "success", remaining_quota="10", quota_unit="token", validity="valid"
            )
        )
        client.app.state.internal_token = "itok"
        missing_idem = client.post(
            "/api/v1/seller-keys",
            json={"platform": "volcano", "api_key": "sk-synthetic-test-key-not-real"},
        )
        assert missing_idem.status_code == 400
        res = client.post(
            "/api/v1/seller-keys",
            json={"platform": "volcano", "api_key": "sk-synthetic-test-key-not-real"},
            headers={"Idempotency-Key": "idem-http-1"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["code"] == "0"
        assert "sk-synthetic" not in res.text
        assert body["data"]["health_state"] == "healthy"
        listed = client.get(
            "/internal/v1/seller-keys/routable", headers={"X-Internal-Token": "itok"}
        )
        assert listed.status_code == 200
        keys = listed.json()["data"]
        assert len(keys) == 1
        assert keys[0]["api_key"] == "sk-synthetic-test-key-not-real"
        assert keys[0]["seller_id"] == str(user)
        key_id = body["data"]["key_id"]
        listed = client.get("/api/v1/seller-keys")
        assert listed.status_code == 200
        one = client.get(f"/api/v1/seller-keys/{key_id}")
        assert one.status_code == 200
        paused = client.post(f"/api/v1/seller-keys/{key_id}/pause")
        assert paused.status_code == 200
        assert paused.json()["data"]["administrative_state"] == "paused"
        # resume needs positive quota validator already set
        resumed = client.post(f"/api/v1/seller-keys/{key_id}/resume")
        assert resumed.status_code == 200
        revoked = client.post(f"/api/v1/seller-keys/{key_id}/revoke")
        assert revoked.status_code == 200
        missing = client.get(f"/api/v1/seller-keys/{uuid.uuid4()}")
        assert missing.status_code == 404


def test_buyer_cannot_onboard() -> None:
    user = uuid.uuid4()
    with TestClient(app) as client:
        client.app.state.actor_override = Actor(
            user_id=user, role="buyer", status="active"
        )
        client.app.state.seller_validator = FakeValidator(
            ValidationSnapshot("success", remaining_quota="1", quota_unit="t")
        )
        res = client.post(
            "/api/v1/seller-keys",
            json={"platform": "volcano", "api_key": "sk-synthetic-test-key-not-real"},
            headers={"Idempotency-Key": "x"},
        )
        assert res.status_code == 403
        assert res.json()["code"] == "UNAUTHORIZED"


def test_issue_proxy_key_tmk_and_auth_hash() -> None:
    user = uuid.uuid4()
    with TestClient(app) as client:
        client.app.state.actor_override = Actor(
            user_id=user, role="buyer", status="active"
        )
        client.app.state.internal_token = "itok"
        res = client.post(
            "/api/v1/proxy-keys",
            json={"platform": "volcano"},
            headers={"Idempotency-Key": "pk-1"},
        )
        assert res.status_code == 200, res.text
        secret = res.json()["data"]["secret"]
        assert secret.startswith("tmk-")
        listed = client.get("/api/v1/proxy-keys")
        assert listed.status_code == 200
        assert "secret" not in listed.text
        from app.domain.proxykeys.service import hash_proxy_secret

        h = hash_proxy_secret(secret, client.app.state.proxy_key_service._pepper)
        look = client.get(
            "/internal/v1/proxy-keys/by-hash",
            params={"hash": h},
            headers={"X-Internal-Token": "itok"},
        )
        assert look.status_code == 200
        assert look.json()["data"]["buyer_id"] == str(user)
        assert "project_mode" in look.json()["data"]
        assert look.json()["data"]["preview_opt_in"] is False
        replay = client.post(
            "/api/v1/proxy-keys",
            json={"platform": "volcano"},
            headers={"Idempotency-Key": "pk-1"},
        )
        assert replay.json()["data"].get("secret") is None
        kid = res.json()["data"]["key_id"]
        gone = client.post(f"/api/v1/proxy-keys/{kid}/revoke")
        assert gone.status_code == 200
        again = client.post(f"/api/v1/proxy-keys/{uuid.uuid4()}/revoke")
        assert again.status_code == 404
        seller = Actor(user_id=user, role="seller", status="active")
        client.app.state.actor_override = seller
        denied = client.post("/api/v1/proxy-keys", json={"platform": "volcano"})
        assert denied.status_code == 403


def test_usage_ingest_idempotent_and_no_fake_zero() -> None:
    with TestClient(app) as client:
        client.app.state.internal_token = "itok"
        payload = {
            "request_id": "rid-u1",
            "platform": "volcano",
            "model": "doubao-pro-32k",
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "usage_source": "official",
            "status_code": 200,
            "end_reason": "success",
        }
        bad_tok = client.post(
            "/internal/v1/usage-observations",
            json=payload,
        )
        assert bad_tok.status_code == 401
        a = client.post(
            "/internal/v1/usage-observations",
            json=payload,
            headers={"X-Internal-Token": "itok"},
        )
        b = client.post(
            "/internal/v1/usage-observations",
            json=payload,
            headers={"X-Internal-Token": "itok"},
        )
        assert a.status_code == 200 and b.status_code == 200
        rec = client.app.state.usage_recorder._store.get("rid-u1")
        assert rec is not None
        assert rec.total_tokens == 3
        fail = client.post(
            "/internal/v1/usage-observations",
            json={
                "request_id": "rid-fail",
                "platform": "volcano",
                "model": "m",
                "usage_source": "not_available",
                "status_code": 502,
                "end_reason": "timeout",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            headers={"X-Internal-Token": "itok"},
        )
        assert fail.status_code == 200
        kid = uuid.uuid4()
        client.app.state.seller_key_store.apply_health(kid, "down")
        patch = client.post(
            f"/internal/v1/seller-keys/{kid}/health",
            json={"health_state": "healthy"},
            headers={"X-Internal-Token": "itok"},
        )
        assert patch.status_code == 200
