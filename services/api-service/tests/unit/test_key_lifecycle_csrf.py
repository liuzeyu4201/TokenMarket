"""Cookie-authenticated key-lifecycle POSTs require Origin and CSRF."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.actors import Actor
from app.config import AuthSettings
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.validator_port import ValidationSnapshot
from app.main import app
from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.session import SESSION_COOKIE_NAME

SIBLING_ORIGIN = "http://127.0.0.1:9999"
ALLOWED_ORIGIN = "http://127.0.0.1:5173"
_CSRF_KEY = "tm_test_" + "c" * 40


class FakeValidator:
    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        return ValidationSnapshot(
            "success", remaining_quota="10", quota_unit="token", validity="valid"
        )


def _settings() -> AuthSettings:
    return AuthSettings(
        csrf_hmac_key_current=_CSRF_KEY,
        csrf_hmac_key_version=1,
        browser_origins=ALLOWED_ORIGIN,
        sms_adapter="synthetic",
    )


def _cookie_headers(
    *,
    origin: str | None,
    csrf: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {"Cookie": f"{SESSION_COOKIE_NAME}=placeholder-session"}
    if origin is not None:
        headers["Origin"] = origin
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if extra:
        headers.update(extra)
    return headers


def _lifecycle_posts(key_id: uuid.UUID) -> list[tuple[str, dict[str, str] | None]]:
    body_needed = {
        "/api/v1/seller-keys": {
            "platform": "volcano",
            "api_key": "sk-synthetic-test-key-not-real",
        },
        "/api/v1/proxy-keys": {"platform": "volcano"},
    }
    paths = [
        "/api/v1/seller-keys",
        f"/api/v1/seller-keys/{key_id}/pause",
        f"/api/v1/seller-keys/{key_id}/resume",
        f"/api/v1/seller-keys/{key_id}/revoke",
        "/api/v1/proxy-keys",
        f"/api/v1/proxy-keys/{key_id}/revoke",
    ]
    return [(p, body_needed.get(p)) for p in paths]


def _prepare_client(
    client: TestClient, *, session_id: uuid.UUID, user: uuid.UUID
) -> None:
    client.app.state.auth_settings = _settings()
    client.app.state.actor_override = Actor(
        user_id=user, role="both", status="active", session_id=session_id
    )
    client.app.state.seller_key_store = MemoryKeyStore()
    client.app.state.seller_encryptor = CredentialEncryptor(b"k" * 32, "v1")
    client.app.state.seller_fp_secret = b"s" * 32
    client.app.state.seller_validator = FakeValidator()


def test_disallowed_sibling_origin_rejects_each_lifecycle_post() -> None:
    user = uuid.uuid4()
    session_id = uuid.uuid4()
    key_id = uuid.uuid4()
    csrf = issue_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id)
    assert verify_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id, csrf)
    with TestClient(app) as client:
        _prepare_client(client, session_id=session_id, user=user)
        for path, json_body in _lifecycle_posts(key_id):
            res = client.post(
                path,
                json=json_body or {},
                headers=_cookie_headers(
                    origin=SIBLING_ORIGIN,
                    csrf=csrf,
                    extra={"Idempotency-Key": "csrf-origin"},
                ),
            )
            assert res.status_code == 403, (path, res.status_code, res.text)
            assert res.json()["code"] == "ORIGIN_REJECTED"


def test_missing_or_mismatched_csrf_fails() -> None:
    user = uuid.uuid4()
    session_id = uuid.uuid4()
    key_id = uuid.uuid4()
    good = issue_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id)
    other = issue_csrf_token(_CSRF_KEY.encode("utf-8"), 1, uuid.uuid4())
    assert good != other
    assert not verify_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id, other)
    with TestClient(app) as client:
        _prepare_client(client, session_id=session_id, user=user)
        for path, json_body in _lifecycle_posts(key_id):
            missing = client.post(
                path,
                json=json_body or {},
                headers=_cookie_headers(
                    origin=ALLOWED_ORIGIN,
                    extra={"Idempotency-Key": "csrf-missing"},
                ),
            )
            assert missing.status_code == 403, (path, missing.text)
            assert missing.json()["code"] == "CSRF_INVALID"
            mismatched = client.post(
                path,
                json=json_body or {},
                headers=_cookie_headers(
                    origin=ALLOWED_ORIGIN,
                    csrf=other,
                    extra={"Idempotency-Key": "csrf-mismatch"},
                ),
            )
            assert mismatched.status_code == 403, (path, mismatched.text)
            assert mismatched.json()["code"] == "CSRF_INVALID"


def test_session_bound_csrf_token_allows_lifecycle_posts() -> None:
    user = uuid.uuid4()
    session_id = uuid.uuid4()
    csrf = issue_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id)
    assert verify_csrf_token(_CSRF_KEY.encode("utf-8"), 1, session_id, csrf)
    with TestClient(app) as client:
        _prepare_client(client, session_id=session_id, user=user)
        issued = client.post(
            "/api/v1/proxy-keys",
            json={"platform": "volcano"},
            headers=_cookie_headers(
                origin=ALLOWED_ORIGIN,
                csrf=csrf,
                extra={"Idempotency-Key": "csrf-ok-proxy"},
            ),
        )
        assert issued.status_code == 200, issued.text
        assert issued.json()["code"] == "0"
        onboard = client.post(
            "/api/v1/seller-keys",
            json={"platform": "volcano", "api_key": "sk-synthetic-test-key-not-real"},
            headers=_cookie_headers(
                origin=ALLOWED_ORIGIN,
                csrf=csrf,
                extra={"Idempotency-Key": "csrf-ok-seller"},
            ),
        )
        assert onboard.status_code == 200, onboard.text
        key_id = uuid.UUID(onboard.json()["data"]["key_id"])
        paused = client.post(
            f"/api/v1/seller-keys/{key_id}/pause",
            json={},
            headers=_cookie_headers(origin=ALLOWED_ORIGIN, csrf=csrf),
        )
        assert paused.status_code == 200, paused.text
        resumed = client.post(
            f"/api/v1/seller-keys/{key_id}/resume",
            json={},
            headers=_cookie_headers(origin=ALLOWED_ORIGIN, csrf=csrf),
        )
        assert resumed.status_code == 200, resumed.text
        revoked = client.post(
            f"/api/v1/seller-keys/{key_id}/revoke",
            json={},
            headers=_cookie_headers(origin=ALLOWED_ORIGIN, csrf=csrf),
        )
        assert revoked.status_code == 200, revoked.text
        proxy_revoke = client.post(
            f"/api/v1/proxy-keys/{uuid.UUID(issued.json()['data']['key_id'])}/revoke",
            json={},
            headers=_cookie_headers(origin=ALLOWED_ORIGIN, csrf=csrf),
        )
        assert proxy_revoke.status_code == 200, proxy_revoke.text
