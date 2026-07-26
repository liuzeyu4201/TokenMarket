"""Integration: anti-enumeration for challenge requests (T058 / US2)."""

from __future__ import annotations

import secrets
import uuid
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_enum_" + secrets.token_urlsafe(32)


class HealthToggleSms(SyntheticSmsAdapter):
    def __init__(self) -> None:
        super().__init__()
        self._ok = True

    def set_health(self, ok: bool) -> None:
        self._ok = ok

    def provider_health_ok(self) -> bool:
        return self._ok


def _set_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MODE", "local")
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_OTP_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_CSRF_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_REFERENCE_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_BROWSER_ORIGINS", ORIGIN)
    monkeypatch.setenv("AUTH_SMS_ADAPTER", "synthetic")
    monkeypatch.setenv("AUTH_DISPATCHER_ENABLED", "0")
    clear_auth_settings_cache()


@pytest.fixture
def enum_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, HealthToggleSms]]:
    _set_env(monkeypatch, auth_migrated_postgres)
    sms = HealthToggleSms()
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = sms
        yield client, sms
    clear_auth_settings_cache()


def _request(client: TestClient, phone: str) -> tuple[int, dict[str, Any], str]:
    res = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={
            "Origin": ORIGIN,
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Request-ID": f"enum-{uuid.uuid4().hex[:8]}",
        },
    )
    return res.status_code, res.json(), res.text


def test_four_account_classes_identical_public_shape(
    enum_client: tuple[TestClient, HealthToggleSms],
    account_factory,
) -> None:
    client, _sms = enum_client
    active = account_factory.create_active()
    suspended = account_factory.create_suspended()
    deleted = account_factory.create_deleted()
    unknown = account_factory.unknown_phone()

    phones = {
        "active": active.phone_normalized,
        "suspended": suspended.phone_normalized,
        "deleted": deleted.phone_normalized,
        "unknown": unknown,
    }
    shapes: dict[str, dict[str, Any]] = {}
    for label, phone in phones.items():
        status, body, text = _request(client, phone)
        assert status == 202, (label, text)
        assert body["code"] == "0"
        assert body["message"]  # neutral message present
        data = body["data"]
        assert set(data.keys()) == {
            "challenge_id",
            "phone_masked",
            "expires_at",
            "resend_available_at",
        }
        assert "*" in data["phone_masked"]
        assert phone not in text
        assert "ACCOUNT" not in text
        assert "NOT_FOUND" not in text
        shapes[label] = {
            "status": status,
            "code": body["code"],
            "message": body["message"],
            "keys": sorted(data.keys()),
        }

    # All four classes share status/code/message/shape
    ref = shapes["active"]
    for label, shape in shapes.items():
        assert shape["status"] == ref["status"], label
        assert shape["code"] == ref["code"], label
        assert shape["message"] == ref["message"], label
        assert shape["keys"] == ref["keys"], label


def test_provider_wide_outage_consistent_delivery_unavailable(
    enum_client: tuple[TestClient, HealthToggleSms],
    account_factory,
) -> None:
    client, sms = enum_client
    sms.set_health(False)
    phones = [
        account_factory.create_active().phone_normalized,
        account_factory.create_suspended().phone_normalized,
        account_factory.create_deleted().phone_normalized,
        account_factory.unknown_phone(),
    ]
    results = [_request(client, p) for p in phones]
    for status, body, text in results:
        assert status == 503
        assert body["code"] == "DELIVERY_UNAVAILABLE"
        assert phones[0] not in text
    codes = {r[1]["code"] for r in results}
    messages = {r[1]["message"] for r in results}
    assert codes == {"DELIVERY_UNAVAILABLE"}
    assert len(messages) == 1


def test_malformed_phone_no_challenge(
    enum_client: tuple[TestClient, HealthToggleSms],
) -> None:
    client, _sms = enum_client
    status, body, _text = _request(client, "not-a-phone")
    assert status == 400
    assert body["code"] == "VALIDATION_ERROR"
    assert "phone" in (body.get("data") or {}).get("errors", {})


def test_rate_limited_neutral_no_dimension_leak(
    enum_client: tuple[TestClient, HealthToggleSms],
    account_factory,
) -> None:
    client, _sms = enum_client
    # Override with tiny phone limit
    client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
        phone_limit=1, ip_limit=100, retry_after_seconds=33
    )
    phone = account_factory.create_active().phone_normalized
    s1, b1, _ = _request(client, phone)
    assert s1 == 202
    s2, b2, text = _request(client, phone)
    assert s2 == 429
    assert b2["code"] == "RATE_LIMITED"
    assert b2["data"]["retry_after_seconds"] >= 1
    assert "phone" not in text.lower() or "phone_masked" not in str(b2.get("data"))
    # Dimension must not appear
    assert "dimension" not in text
    assert '"ip"' not in text
