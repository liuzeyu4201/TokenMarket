"""HTTP workspace switch (SF09)."""

from __future__ import annotations

import secrets
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.domain.users.models import UserRole
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.sms.synthetic import SyntheticSmsAdapter
from tests.integration.test_session_lifecycle import _login_client

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_ws_" + secrets.token_urlsafe(32)


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
def ws_client(
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


def test_both_user_switches_workspace(
    ws_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(role=UserRole.both)
    csrf = _login_client(ws_client, user.phone_normalized, auth_migrated_postgres)
    boot = ws_client.get("/api/v1/auth/session")
    assert boot.json()["data"]["workspace"] == "buyer"

    denied_csrf = ws_client.post(
        "/api/v1/auth/workspace",
        json={"workspace": "seller"},
        headers={"Origin": ORIGIN},
    )
    assert denied_csrf.status_code == 403

    switched = ws_client.post(
        "/api/v1/auth/workspace",
        json={"workspace": "seller"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["data"]["workspace"] == "seller"

    seller_ok = ws_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "seller_key.register", "workspace": "buyer"},
        headers={"Origin": ORIGIN},
    )
    assert seller_ok.status_code == 200, seller_ok.text

    buyer_denied = ws_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
        headers={"Origin": ORIGIN},
    )
    assert buyer_denied.status_code == 403
    assert buyer_denied.json()["code"] == "FORBIDDEN_ROLE"


def test_buyer_cannot_switch_to_seller(
    ws_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(role=UserRole.buyer)
    csrf = _login_client(ws_client, user.phone_normalized, auth_migrated_postgres)
    res = ws_client.post(
        "/api/v1/auth/workspace",
        json={"workspace": "seller"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN_ROLE"
    boot = ws_client.get("/api/v1/auth/session")
    assert boot.json()["data"]["workspace"] == "buyer"
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM authentication_security_events "
                "WHERE event_type = 'workspace_switch_denied' "
                "AND user_id = CAST(:id AS uuid)"
            ),
            {"id": str(user.id)},
        ).scalar_one()
    engine.dispose()
    assert int(n) >= 1
