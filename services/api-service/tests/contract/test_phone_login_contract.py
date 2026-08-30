"""Contract tests for phone-auth-session OpenAPI surface (T033)."""

from __future__ import annotations

import asyncio
import re
import secrets
import time
import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import clear_auth_settings_cache, load_auth_settings
from app.dependencies import create_session_engine
from app.dispatch.auth_delivery import AuthDeliveryDispatcher
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.security.otp import derive_otp
from app.security.session import SESSION_COOKIE_NAME
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_contract_" + secrets.token_urlsafe(32)


def _auth_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
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


async def _deliver_all(database_url: str) -> None:
    """Run dispatcher on a dedicated async engine (own event loop)."""
    engine = create_session_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = load_auth_settings()
    dispatcher = AuthDeliveryDispatcher(
        factory, settings, SyntheticSmsAdapter(), owner="contract-dispatch"
    )
    for _ in range(30):
        n = await dispatcher.run_once()
        if n == 0:
            break
    await engine.dispose()


def _wait_delivered(
    database_url: str, challenge_id: str, *, timeout: float = 10.0
) -> None:
    asyncio.run(_deliver_all(database_url))
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with engine.connect() as conn:
                state = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": challenge_id},
                ).scalar_one()
            if state in ("delivered", "delivery_failed"):
                assert state == "delivered"
                return
            time.sleep(0.05)
            asyncio.run(_deliver_all(database_url))
        raise AssertionError(f"challenge not delivered: last state={state!r}")
    finally:
        engine.dispose()


@pytest.fixture
def contract_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _auth_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        from app.auth_rate_limit import MemoryAuthRateLimiter

        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def test_verification_challenge_and_session_operations_exist(
    contract_client: TestClient,
) -> None:
    res = contract_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": "13800138000"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "ORIGIN_REJECTED"

    res2 = contract_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": str(uuid.uuid4()), "code": "012345"},
    )
    assert res2.status_code == 403
    assert res2.json()["code"] == "ORIGIN_REJECTED"


def test_challenge_accepted_shape_and_idempotency_header(
    contract_client: TestClient,
    account_factory,
) -> None:
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    res = contract_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={
            "Origin": ORIGIN,
            "Idempotency-Key": key,
            "X-Request-ID": "contract-challenge-1",
        },
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["code"] == "0"
    data = body["data"]
    assert set(data.keys()) >= {
        "challenge_id",
        "phone_masked",
        "expires_at",
        "resend_available_at",
    }
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        data["challenge_id"],
        re.I,
    )
    assert "*" in data["phone_masked"]
    assert user.phone_normalized not in res.text
    assert "otp" not in res.text.lower()
    assert res.headers.get("cache-control", "").lower() == "no-store"

    res2 = contract_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
    )
    assert res2.status_code == 202
    assert res2.json()["data"]["challenge_id"] == data["challenge_id"]


def test_register_requires_verification(contract_client: TestClient) -> None:
    phone = f"138{uuid.uuid4().int % 10**8:08d}"[:11]
    phone = "138" + phone[3:]
    res = contract_client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "契约用户", "role": "buyer"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 403, res.text
    assert res.json()["code"] == "AUTH_VERIFICATION_REQUIRED"


def test_session_set_cookie_attributes_and_no_credential_in_body(
    contract_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    ch = contract_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
    )
    assert ch.status_code == 202, ch.text
    challenge_id = ch.json()["data"]["challenge_id"]

    _wait_delivered(auth_migrated_postgres, challenge_id)

    settings = load_auth_settings()
    code = derive_otp(settings.key_material("otp").current, challenge_id)

    res = contract_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN, "X-Request-ID": "contract-session-1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["code"] == "0"
    data = body["data"]
    for field in (
        "user_id",
        "nickname",
        "phone_masked",
        "role",
        "expires_at",
        "csrf_token",
    ):
        assert field in data
    assert SESSION_COOKIE_NAME not in res.text
    assert "cookie_value" not in res.text.lower()
    assert data["csrf_token"]
    assert code not in res.text

    set_cookie = res.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    lower = set_cookie.lower()
    assert "secure" in lower
    assert "httponly" in lower
    assert "samesite=lax" in lower
    assert "path=/" in lower
    assert "max-age=3600" in lower
    assert "domain=" not in lower
