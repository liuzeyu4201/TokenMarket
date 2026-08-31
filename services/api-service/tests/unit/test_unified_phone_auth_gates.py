"""Unit tests for unified phone auth HTTP gates (SF06)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.security.profile_token import profile_token_digest
from app.security.session import token_digest


def test_register_without_profile_cookie_is_rejected() -> None:
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "phone": "13800138000",
                "nickname": "枚举探针",
                "role": "buyer",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    assert res.status_code == 403
    body = res.json()
    assert body["code"] == "AUTH_VERIFICATION_REQUIRED"
    assert "PHONE_ALREADY_REGISTERED" not in res.text
    assert "13800138000" not in res.text


def test_profile_digest_is_domain_separated() -> None:
    key = b"k" * 32
    opaque = "opaque-secret-material-value"
    assert profile_token_digest(key, opaque) != token_digest(key, opaque)
