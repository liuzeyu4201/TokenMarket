"""Integration: session generation, revoke-all, security summary (SF07)."""

from __future__ import annotations

import secrets
import time
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.security.session import SESSION_COOKIE_NAME
from app.sms.synthetic import SyntheticSmsAdapter
from tests.integration.test_session_lifecycle import _login_client

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_sgen_" + secrets.token_urlsafe(32)


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
def gen_client(
    auth_migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    _set_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def _key_counts(url: str) -> tuple[int, int]:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        proxy = conn.execute(text("SELECT count(*) FROM proxy_keys")).scalar_one()
        seller = conn.execute(text("SELECT count(*) FROM seller_api_keys")).scalar_one()
    engine.dispose()
    return int(proxy), int(seller)


def test_second_login_bumps_generation_and_preserves_keys(
    gen_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    before = _key_counts(auth_migrated_postgres)
    csrf_a = _login_client(gen_client, user.phone_normalized, auth_migrated_postgres)
    cookie_a = gen_client.cookies.get(SESSION_COOKIE_NAME)
    assert csrf_a and cookie_a

    with TestClient(app) as device_b:
        device_b.app.state.rate_limiter = MemoryRateLimiter()
        device_b.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        device_b.app.state.sms_adapter = SyntheticSmsAdapter()
        _login_client(device_b, user.phone_normalized, auth_migrated_postgres)
        start = time.monotonic()
        assert device_b.get("/api/v1/auth/session").status_code == 200
        elapsed = time.monotonic() - start
        assert elapsed < 1.0

    try:
        gen_client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        gen_client.cookies.clear()
    gen_client.cookies.set(SESSION_COOKIE_NAME, cookie_a, path="/")
    res = gen_client.get("/api/v1/auth/session")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
    assert before == _key_counts(auth_migrated_postgres)

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        gen = conn.execute(
            text("SELECT session_generation FROM users WHERE id = CAST(:id AS uuid)"),
            {"id": str(user.id)},
        ).scalar_one()
        active = conn.execute(
            text(
                "SELECT count(*) FROM auth_sessions "
                "WHERE user_id = CAST(:id AS uuid) AND revoked_at IS NULL"
            ),
            {"id": str(user.id)},
        ).scalar_one()
    engine.dispose()
    assert int(gen) >= 2
    assert int(active) == 1


def test_revoke_all_requires_csrf_and_bumps_generation(
    gen_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    csrf = _login_client(gen_client, user.phone_normalized, auth_migrated_postgres)
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT session_generation FROM users WHERE id = CAST(:id AS uuid)"),
            {"id": str(user.id)},
        ).scalar_one()

    denied = gen_client.post(
        "/api/v1/auth/session-revocations",
        json={"scope": "all"},
        headers={"Origin": ORIGIN},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "CSRF_INVALID"

    with engine.connect() as conn:
        mid = conn.execute(
            text("SELECT session_generation FROM users WHERE id = CAST(:id AS uuid)"),
            {"id": str(user.id)},
        ).scalar_one()
    assert int(mid) == int(before)

    done = gen_client.post(
        "/api/v1/auth/session-revocations",
        json={"scope": "all"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert done.status_code == 200, done.text
    assert done.json()["data"]["scope"] == "all"
    boot = gen_client.get("/api/v1/auth/session")
    assert boot.status_code == 401

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT session_generation FROM users WHERE id = CAST(:id AS uuid)"),
            {"id": str(user.id)},
        ).scalar_one()
        events = conn.execute(
            text(
                "SELECT count(*) FROM authentication_security_events "
                "WHERE user_id = CAST(:id AS uuid) "
                "AND event_type = 'session_revoked_all'"
            ),
            {"id": str(user.id)},
        ).scalar_one()
        active = conn.execute(
            text(
                "SELECT count(*) FROM auth_sessions "
                "WHERE user_id = CAST(:id AS uuid) AND revoked_at IS NULL"
            ),
            {"id": str(user.id)},
        ).scalar_one()
    engine.dispose()
    assert int(after) == int(before) + 1
    assert int(events) == 1
    assert int(active) == 0


def test_security_summary_authenticated_has_no_token(
    gen_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    _login_client(gen_client, user.phone_normalized, auth_migrated_postgres)
    res = gen_client.get("/api/v1/auth/security-summary")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["code"] == "0"
    session = body["data"]["session"]
    assert "generation" in session
    assert "issued_at" in session
    assert "token" not in res.text.lower()
    assert user.phone_normalized not in res.text

    try:
        gen_client.cookies.jar.clear()
    except Exception:  # noqa: BLE001
        gen_client.cookies.clear()
    anon = gen_client.get("/api/v1/auth/security-summary")
    assert anon.status_code == 401
    assert anon.json()["code"] == "UNAUTHENTICATED"


def test_guessed_cookie_does_not_bootstrap(gen_client: TestClient) -> None:
    gen_client.cookies.set(SESSION_COOKIE_NAME, "1." + "a" * 43, path="/")
    res = gen_client.get("/api/v1/auth/session")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
    assert "token" not in res.text.lower()
