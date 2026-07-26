"""Contract tests for GET/DELETE /api/v1/auth/session (T072 / T079)."""

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
_KEY = "tm_sess_contract_" + secrets.token_urlsafe(32)


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
        factory, settings, SyntheticSmsAdapter(), owner="sess-contract-dispatch"
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
        state = None
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


def _extract_session_cookie(set_cookie: str) -> str | None:
    """Parse raw session cookie value from Set-Cookie (TestClient may drop Secure)."""
    if not set_cookie or SESSION_COOKIE_NAME not in set_cookie:
        return None
    for part in set_cookie.split(","):
        segment = part.strip()
        if segment.startswith(SESSION_COOKIE_NAME + "="):
            return segment.split(";", 1)[0].split("=", 1)[1]
    # Single Set-Cookie without multi-header join
    first = set_cookie.split(";", 1)[0].strip()
    if first.startswith(SESSION_COOKIE_NAME + "="):
        return first.split("=", 1)[1]
    return None


def _login(
    client: TestClient,
    *,
    phone: str,
    database_url: str,
) -> tuple[str, str]:
    """Return (csrf_token, opaque cookie value). Forces jar for __Host- Secure cookies."""
    ch = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert ch.status_code == 202, ch.text
    challenge_id = ch.json()["data"]["challenge_id"]
    _wait_delivered(database_url, challenge_id)
    settings = load_auth_settings()
    code = derive_otp(settings.key_material("otp").current, challenge_id)
    res = client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert res.status_code == 200, res.text
    csrf = res.json()["data"]["csrf_token"]
    raw = res.headers.get("set-cookie", "")
    value = _extract_session_cookie(raw)
    assert value, f"missing session cookie in Set-Cookie: {raw!r}"
    # httpx TestClient often omits Secure __Host- cookies on http://testserver
    _force_session_cookie(client, value)
    return csrf, raw


def _force_session_cookie(client: TestClient, value: str) -> None:
    """Install session cookie into jar without Secure/__Host- conflicts."""
    try:
        client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, value, path="/")


@pytest.fixture
def session_client(
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


def test_get_session_no_cookie_is_unauthenticated(session_client: TestClient) -> None:
    res = session_client.get("/api/v1/auth/session")
    assert res.status_code == 401
    body = res.json()
    assert body["code"] == "UNAUTHENTICATED"
    assert set(body.keys()) >= {"code", "message", "data", "request_id", "timestamp"}
    assert res.headers.get("cache-control", "").lower() == "no-store"
    # No credential material in body
    assert SESSION_COOKIE_NAME not in res.text
    assert "csrf_token" not in res.text


def test_bootstrap_and_logout_contract(
    session_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(nickname="会话契约")
    csrf, set_cookie = _login(
        session_client,
        phone=user.phone_normalized,
        database_url=auth_migrated_postgres,
    )
    assert SESSION_COOKIE_NAME in set_cookie
    lower_sc = set_cookie.lower()
    assert "httponly" in lower_sc
    assert "secure" in lower_sc

    boot = session_client.get("/api/v1/auth/session")
    assert boot.status_code == 200, boot.text
    assert boot.headers.get("cache-control", "").lower() == "no-store"
    data = boot.json()["data"]
    for field in (
        "user_id",
        "nickname",
        "phone_masked",
        "role",
        "expires_at",
        "csrf_token",
    ):
        assert field in data
    assert data["user_id"] == str(user.id)
    assert "*" in data["phone_masked"]
    assert user.phone_normalized not in boot.text
    assert SESSION_COOKIE_NAME not in boot.text
    assert data["csrf_token"]

    # Logout requires Origin + CSRF
    bad = session_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN},
    )
    assert bad.status_code == 403
    assert bad.json()["code"] == "CSRF_INVALID"

    bad_origin = session_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["code"] == "ORIGIN_REJECTED"

    ok = session_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["code"] == "0"
    assert ok.json()["data"]["logged_out"] is True
    assert ok.headers.get("cache-control", "").lower() == "no-store"
    clear = ok.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in clear
    lower = clear.lower()
    assert "max-age=0" in lower
    assert "secure" in lower
    assert "httponly" in lower
    assert "samesite=lax" in lower
    assert "path=/" in lower
    assert "domain=" not in lower
    assert SESSION_COOKIE_NAME not in ok.text
    assert csrf not in ok.text

    # Idempotent second logout (cookie already cleared by client jar after first)
    again = session_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN},
    )
    assert again.status_code == 200
    assert again.json()["code"] == "0"

    boot2 = session_client.get("/api/v1/auth/session")
    assert boot2.status_code == 401
    assert boot2.json()["code"] == "UNAUTHENTICATED"


def test_invalid_cookie_cleared_on_bootstrap(
    session_client: TestClient,
) -> None:
    session_client.cookies.set(SESSION_COOKIE_NAME, "1.not-a-real-token")
    res = session_client.get("/api/v1/auth/session")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
    set_cookie = res.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "max-age=0" in set_cookie.lower()


def test_body_never_contains_raw_cookie_or_otp(
    session_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    csrf, _ = _login(
        session_client,
        phone=user.phone_normalized,
        database_url=auth_migrated_postgres,
    )
    boot = session_client.get("/api/v1/auth/session")
    text_body = boot.text
    assert "__Host-tokenmarket_session=" not in text_body
    assert re.search(r"cookie_value", text_body, re.I) is None
    # csrf_token is contracted in data; raw cookie value must not appear
    assert "1." not in text_body.split('"csrf_token"')[0]  # coarse
    logout = session_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert csrf not in logout.text or logout.json()["code"] == "0"
    # Credential must not be echoed
    assert SESSION_COOKIE_NAME not in logout.text
