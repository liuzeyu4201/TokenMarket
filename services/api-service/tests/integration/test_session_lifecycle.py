"""Integration: session bootstrap, replacement, logout retry, restart (T074)."""

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
_KEY = "tm_sess_life_" + secrets.token_urlsafe(32)


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
        factory, settings, SyntheticSmsAdapter(), owner="life-dispatch"
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


def _session_cookie_value(set_cookie: str) -> str:
    first = set_cookie.split(";", 1)[0].strip()
    assert first.startswith(SESSION_COOKIE_NAME + "="), set_cookie
    return first.split("=", 1)[1]


def _login_client(
    client: TestClient,
    phone: str,
    database_url: str,
) -> str:
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
    value = _session_cookie_value(res.headers.get("set-cookie", ""))
    try:
        client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, value, path="/")
    return res.json()["data"]["csrf_token"]


@pytest.fixture
def life_client(
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


def test_refresh_bootstrap_restores_session(
    life_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(nickname="刷新用户")
    csrf = _login_client(life_client, user.phone_normalized, auth_migrated_postgres)
    assert csrf
    boot = life_client.get("/api/v1/auth/session")
    assert boot.status_code == 200
    assert boot.json()["data"]["nickname"] == "刷新用户"
    assert boot.json()["data"]["csrf_token"]


def test_new_login_replaces_old_device_within_one_second(
    life_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = account_factory.create_active()
    # Device A
    csrf_a = _login_client(life_client, user.phone_normalized, auth_migrated_postgres)
    cookie_a = life_client.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_a

    # Device B: separate client jar
    with TestClient(app) as device_b:
        device_b.app.state.rate_limiter = MemoryRateLimiter()
        device_b.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        device_b.app.state.sms_adapter = SyntheticSmsAdapter()
        csrf_b = _login_client(device_b, user.phone_normalized, auth_migrated_postgres)
        assert csrf_b
        assert device_b.get("/api/v1/auth/session").status_code == 200

    # Device A cookie must fail quickly
    start = time.monotonic()
    try:
        life_client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        life_client.cookies.clear()
    life_client.cookies.set(SESSION_COOKIE_NAME, cookie_a, path="/")
    res = life_client.get("/api/v1/auth/session")
    elapsed = time.monotonic() - start
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
    assert elapsed < 1.0

    # Old device logout is idempotent for already-revoked token
    try:
        life_client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        life_client.cookies.clear()
    life_client.cookies.set(SESSION_COOKIE_NAME, cookie_a, path="/")
    logout_old = life_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_a},
    )
    assert logout_old.status_code == 200


def test_account_status_rechecked_on_bootstrap(
    life_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    _login_client(life_client, user.phone_normalized, auth_migrated_postgres)
    assert life_client.get("/api/v1/auth/session").status_code == 200

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE users SET status = 'suspended' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": str(user.id)},
            )
    finally:
        engine.dispose()

    res = life_client.get("/api/v1/auth/session")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


def test_logout_retry_after_response_loss(
    life_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    csrf = _login_client(life_client, user.phone_normalized, auth_migrated_postgres)
    first = life_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert first.status_code == 200
    # Simulate client retry with same CSRF after response loss
    life_client.cookies.set(
        SESSION_COOKIE_NAME,
        (
            first.headers.get("set-cookie", "").split(";")[0].split("=", 1)[-1]
            if False
            else ""
        ),
    )
    # Cookie cleared; retry still success
    second = life_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert second.status_code == 200
    assert second.json()["code"] == "0"


def test_bootstrap_survives_process_restart_simulation(
    auth_migrated_postgres: str,
    account_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New TestClient = new process state; durable session still bootstraps."""
    _auth_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as c1:
        c1.app.state.rate_limiter = MemoryRateLimiter()
        c1.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        c1.app.state.sms_adapter = SyntheticSmsAdapter()
        user = account_factory.create_active()
        _login_client(c1, user.phone_normalized, auth_migrated_postgres)
        cookie = c1.cookies.get(SESSION_COOKIE_NAME)
        assert cookie

    with TestClient(app) as c2:
        c2.app.state.rate_limiter = MemoryRateLimiter()
        c2.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        c2.app.state.sms_adapter = SyntheticSmsAdapter()
        try:
            c2.cookies.jar.clear()
        except Exception:  # noqa: BLE001
            c2.cookies.clear()
        c2.cookies.set(SESSION_COOKIE_NAME, cookie, path="/")
        res = c2.get("/api/v1/auth/session")
        assert res.status_code == 200, res.text
        assert res.json()["data"]["user_id"] == str(user.id)
    clear_auth_settings_cache()
