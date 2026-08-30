"""Integration: phone OTP login happy path (T034)."""

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
from app.sms.fake import BlockingSmsFake
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_happy_" + secrets.token_urlsafe(32)


def _set_auth_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
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
def happy_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _set_auth_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=10_000, ip_limit=10_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


async def _run_dispatcher(
    database_url: str,
    sms: BlockingSmsFake | SyntheticSmsAdapter,
    *,
    times: int = 5,
) -> AuthDeliveryDispatcher:
    engine = create_session_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings = load_auth_settings()
    dispatcher = AuthDeliveryDispatcher(
        factory, settings, sms, owner=f"test-{secrets.token_hex(4)}"
    )
    for _ in range(times):
        await dispatcher.run_once()
    await engine.dispose()
    return dispatcher


async def _drain_to_state(
    database_url: str,
    challenge_id: str,
    sms: BlockingSmsFake | SyntheticSmsAdapter,
    *,
    timeout: float = 10.0,
) -> str:
    engine_sync = create_engine(database_url, pool_pre_ping=True)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            async_engine = create_session_engine(database_url)
            factory = async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )
            settings = load_auth_settings()
            dispatcher = AuthDeliveryDispatcher(
                factory, settings, sms, owner=f"drain-{secrets.token_hex(3)}"
            )
            await dispatcher.run_once()
            await async_engine.dispose()
            with engine_sync.connect() as conn:
                state = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": challenge_id},
                ).scalar_one()
            if state in ("delivered", "delivery_failed", "superseded"):
                return str(state)
            await asyncio.sleep(0.05)
        raise AssertionError("challenge not terminal")
    finally:
        engine_sync.dispose()


def test_happy_path_pending_to_session(
    happy_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active(nickname="登录用户")
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    fake = BlockingSmsFake()

    # Prove 202 commits before recipient send: block fake and assert pending.
    fake.block()
    key = str(uuid.uuid4())
    res = happy_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": key, "X-Request-ID": "hp-1"},
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["code"] == "0"
    challenge_id = body["data"]["challenge_id"]
    assert "*" in body["data"]["phone_masked"]
    assert user.phone_normalized not in res.text

    with engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM verification_challenges WHERE id = CAST(:id AS uuid)"
            ),
            {"id": challenge_id},
        ).scalar_one()
        assert state == "pending_delivery"
        row = conn.execute(
            text(
                "SELECT code_digest, code_salt FROM verification_challenges "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": challenge_id},
        ).one()
        assert row[0] is not None and row[1] is not None

    async def _blocked_path() -> None:
        async_engine = create_session_engine(auth_migrated_postgres)
        factory = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )
        settings = load_auth_settings()
        dispatcher = AuthDeliveryDispatcher(factory, settings, fake, owner="block-test")
        task = asyncio.create_task(dispatcher.run_once())
        await asyncio.wait_for(fake.send_entered.wait(), timeout=5.0)
        sync = create_engine(auth_migrated_postgres, pool_pre_ping=True)
        try:
            with sync.connect() as conn:
                st = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": challenge_id},
                ).scalar_one()
            assert st == "dispatching"
        finally:
            sync.dispose()
        fake.unblock()
        await task
        await async_engine.dispose()

    asyncio.run(_blocked_path())

    with engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM verification_challenges WHERE id = CAST(:id AS uuid)"
            ),
            {"id": challenge_id},
        ).scalar_one()
    assert state == "delivered"

    settings = load_auth_settings()
    code = derive_otp(settings.key_material("otp").current, challenge_id)
    assert len(code) == 6

    session_res = happy_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN, "X-Request-ID": "hp-2"},
    )
    assert session_res.status_code == 200, session_res.text
    sbody = session_res.json()
    assert sbody["code"] == "0"
    assert sbody["data"]["nickname"] == "登录用户"
    assert sbody["data"]["user_id"] == str(user.id)
    assert "csrf_token" in sbody["data"]
    assert code not in session_res.text
    assert SESSION_COOKIE_NAME in session_res.headers.get("set-cookie", "")

    with engine.connect() as conn:
        ch_state = conn.execute(
            text(
                "SELECT state, code_digest FROM verification_challenges "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": challenge_id},
        ).one()
        assert ch_state[0] == "consumed"
        assert ch_state[1] is None
        sessions = conn.execute(
            text(
                "SELECT count(*) FROM auth_sessions "
                "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
            ),
            {"uid": str(user.id)},
        ).scalar_one()
        assert sessions == 1
        expires = conn.execute(
            text(
                "SELECT expires_at - issued_at FROM auth_sessions "
                "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
            ),
            {"uid": str(user.id)},
        ).scalar_one()
        assert expires.total_seconds() >= 3590
        assert expires.total_seconds() <= 3660
        events = conn.execute(
            text("SELECT event_type, reason_code FROM authentication_security_events")
        ).fetchall()
        assert events
        for _etype, reason in events:
            assert user.phone_normalized not in str(reason)

    engine.dispose()


def test_old_challenge_superseded_on_new_request(
    happy_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    sms = SyntheticSmsAdapter()

    r1 = happy_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r1.status_code == 202
    cid1 = r1.json()["data"]["challenge_id"]
    state = asyncio.run(_drain_to_state(auth_migrated_postgres, cid1, sms))
    assert state == "delivered"

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE verification_challenges "
                "SET created_at = NOW() - INTERVAL '61 seconds' "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": cid1},
        )

    r2 = happy_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": user.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r2.status_code == 202
    cid2 = r2.json()["data"]["challenge_id"]
    assert cid2 != cid1

    with engine.connect() as conn:
        st1 = conn.execute(
            text(
                "SELECT state FROM verification_challenges WHERE id = CAST(:id AS uuid)"
            ),
            {"id": cid1},
        ).scalar_one()
    assert st1 == "superseded"
    engine.dispose()


def test_decoy_produces_zero_sessions(
    happy_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    unknown = account_factory.unknown_phone()
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    sms = SyntheticSmsAdapter()

    res = happy_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": unknown},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 202
    assert res.json()["code"] == "0"
    challenge_id = res.json()["data"]["challenge_id"]

    state = asyncio.run(_drain_to_state(auth_migrated_postgres, challenge_id, sms))
    assert state == "delivered"

    with engine.connect() as conn:
        user_id = conn.execute(
            text(
                "SELECT user_id FROM verification_challenges "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": challenge_id},
        ).scalar_one()
        assert user_id is None

    settings = load_auth_settings()
    code = derive_otp(settings.key_material("otp").current, challenge_id)
    session_res = happy_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert session_res.status_code == 200
    assert session_res.json()["code"] == "PROFILE_COMPLETION_REQUIRED"
    assert SESSION_COOKIE_NAME not in session_res.headers.get("set-cookie", "")

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()
        assert count == 0
        users = conn.execute(
            text("SELECT count(*) FROM users WHERE phone_normalized = :p"),
            {"p": unknown},
        ).scalar_one()
        assert users == 0
    engine.dispose()
