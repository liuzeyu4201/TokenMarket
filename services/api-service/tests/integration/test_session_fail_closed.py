"""Fail-closed session paths: DB down, unknown key version,
Redis independence (T075)."""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth_rate_limit import MemoryAuthRateLimiter
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
_KEY = "tm_sess_fc_" + secrets.token_urlsafe(32)


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
    engine = create_session_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = load_auth_settings()
    dispatcher = AuthDeliveryDispatcher(
        factory, settings, SyntheticSmsAdapter(), owner="fc-dispatch"
    )
    for _ in range(30):
        if await dispatcher.run_once() == 0:
            break
    await engine.dispose()


def _wait_delivered(database_url: str, challenge_id: str) -> None:
    asyncio.run(_deliver_all(database_url))
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            with engine.connect() as conn:
                state = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": challenge_id},
                ).scalar_one()
            if state == "delivered":
                return
            time.sleep(0.05)
            asyncio.run(_deliver_all(database_url))
        raise AssertionError("not delivered")
    finally:
        engine.dispose()


def _login(client: TestClient, phone: str, database_url: str) -> str:
    ch = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert ch.status_code == 202, ch.text
    cid = ch.json()["data"]["challenge_id"]
    _wait_delivered(database_url, cid)
    code = derive_otp(load_auth_settings().key_material("otp").current, cid)
    res = client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": cid, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert res.status_code == 200, res.text
    set_cookie = res.headers.get("set-cookie", "")
    first = set_cookie.split(";", 1)[0].strip()
    assert first.startswith(SESSION_COOKIE_NAME + "="), set_cookie
    try:
        client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, first.split("=", 1)[1], path="/")
    return res.json()["data"]["csrf_token"]


@pytest.fixture
def fc_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _auth_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def test_db_down_returns_503_no_protected_data(
    fc_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(nickname="机密昵称勿泄漏")
    _login(fc_client, user.phone_normalized, auth_migrated_postgres)

    # Simulate dependency unavailable by removing session factory.
    prev = fc_client.app.state.session_factory
    fc_client.app.state.session_factory = None
    try:
        res = fc_client.get("/api/v1/auth/session")
        assert res.status_code == 503
        body = res.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert "机密" not in res.text
        assert user.phone_normalized not in res.text
        assert SESSION_COOKIE_NAME not in res.text
    finally:
        fc_client.app.state.session_factory = prev


def test_unknown_key_version_returns_503(
    fc_client: TestClient,
) -> None:
    fc_client.cookies.set(SESSION_COOKIE_NAME, "99." + "a" * 48)
    res = fc_client.get("/api/v1/auth/session")
    assert res.status_code == 503
    assert res.json()["code"] == "SERVICE_UNAVAILABLE"
    # Fail closed: do not claim unauthenticated (would invite wrong UX).
    assert res.json()["code"] != "UNAUTHENTICATED"


def test_redis_down_does_not_break_existing_session_check(
    fc_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    _login(fc_client, user.phone_normalized, auth_migrated_postgres)

    # Registration rate limiter fail-closed must not affect session bootstrap.
    fc_client.app.state.rate_limiter = MemoryRateLimiter(fail=True)

    res = fc_client.get("/api/v1/auth/session")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["user_id"] == str(user.id)
    assert "phone_masked" in res.json()["data"]
