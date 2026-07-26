"""Integration: concurrent OTP verify and dual-device login (T057 / US2)."""

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
from app.domain.authentication.session_service import SessionService
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.security.otp import derive_otp
from app.security.session import SESSION_COOKIE_NAME
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_conc_" + secrets.token_urlsafe(32)


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
def conc_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
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


async def _drain(
    database_url: str,
    challenge_id: str,
    *,
    timeout: float = 10.0,
) -> str:
    sms = SyntheticSmsAdapter()
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
                factory, settings, sms, owner=f"c-{secrets.token_hex(3)}"
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


def _request_delivered_challenge(
    client: TestClient,
    database_url: str,
    phone: str,
) -> tuple[str, str]:
    res = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 202, res.text
    cid = res.json()["data"]["challenge_id"]
    state = asyncio.run(_drain(database_url, cid))
    assert state == "delivered"
    settings = load_auth_settings()
    code = derive_otp(settings.key_material("otp").current, cid)
    return cid, code


def test_100_concurrent_correct_otp_at_most_one_session(
    conc_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    cid, code = _request_delivered_challenge(
        conc_client, auth_migrated_postgres, user.phone_normalized
    )
    challenge_id = uuid.UUID(cid)
    settings = load_auth_settings()

    async def _run() -> list[str]:
        engine = create_session_engine(auth_migrated_postgres)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async def one_attempt(i: int) -> str:
            async with factory() as session:
                svc = SessionService(session, settings)
                result = await svc.create_session(
                    challenge_id=challenge_id,
                    code=code,
                    request_id=f"conc-{i}",
                )
                return result.code

        codes = await asyncio.gather(*[one_attempt(i) for i in range(100)])
        await engine.dispose()
        return list(codes)

    codes = asyncio.run(_run())
    successes = [c for c in codes if c == "0"]
    assert len(successes) == 1, codes[:20]
    others = [c for c in codes if c != "0"]
    assert len(others) == 99
    for c in others:
        assert c in (
            "VERIFICATION_FAILED",
            "CHALLENGE_UNAVAILABLE",
            "CHALLENGE_EXPIRED",
        )

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            active = conn.execute(
                text(
                    "SELECT count(*) FROM auth_sessions "
                    "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
                ),
                {"uid": str(user.id)},
            ).scalar_one()
            assert int(active) == 1
            ch_state = conn.execute(
                text(
                    "SELECT state FROM verification_challenges "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": cid},
            ).scalar_one()
            assert ch_state == "consumed"
    finally:
        engine.dispose()


def test_dual_device_login_single_active(
    conc_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    """Device B login revokes device A; only one active session remains."""
    user = account_factory.create_active()
    cid1, code1 = _request_delivered_challenge(
        conc_client, auth_migrated_postgres, user.phone_normalized
    )
    r1 = conc_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": cid1, "code": code1},
        headers={"Origin": ORIGIN},
    )
    assert r1.status_code == 200
    cookie_a = r1.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie_a

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE verification_challenges "
                    "SET created_at = NOW() - INTERVAL '61 seconds' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": cid1},
            )
    finally:
        engine.dispose()

    cid2, code2 = _request_delivered_challenge(
        conc_client, auth_migrated_postgres, user.phone_normalized
    )
    settings = load_auth_settings()

    async def _concurrent_second_login() -> list[str]:
        """100 concurrent correct submissions of device-B challenge."""
        engine = create_session_engine(auth_migrated_postgres)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        cid = uuid.UUID(cid2)

        async def one(i: int) -> str:
            async with factory() as session:
                svc = SessionService(session, settings)
                result = await svc.create_session(
                    challenge_id=cid,
                    code=code2,
                    request_id=f"devb-{i}",
                )
                return result.code

        codes = await asyncio.gather(*[one(i) for i in range(100)])
        await engine.dispose()
        return list(codes)

    codes = asyncio.run(_concurrent_second_login())
    assert codes.count("0") == 1

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            active = conn.execute(
                text(
                    "SELECT count(*) FROM auth_sessions "
                    "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
                ),
                {"uid": str(user.id)},
            ).scalar_one()
            assert int(active) == 1
            revoked = conn.execute(
                text(
                    "SELECT count(*) FROM auth_sessions "
                    "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NOT NULL"
                ),
                {"uid": str(user.id)},
            ).scalar_one()
            assert int(revoked) >= 1
    finally:
        engine.dispose()

    # Old device cookie rejected immediately (≤1s).
    get_res = conc_client.get(
        "/api/v1/auth/session",
        headers={"Cookie": cookie_a.split(";")[0]},
    )
    if get_res.status_code != 404:
        assert get_res.status_code == 401
        assert get_res.json()["code"] == "UNAUTHENTICATED"


def test_dual_device_100_login_rounds_single_active(
    conc_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    """SC-002a: 100 sequential dual-device login rounds → one active session each.

    Each round: device A login → device B login (revokes A) → assert single active
    and A cookie rejected within 1s. Round count is 100 under ``TM_PERF=1`` /
    ``AUTH_SC002A_FULL=1``, else 5 for CI speed.
    """
    import os
    import time as time_mod

    full = os.environ.get("TM_PERF") == "1" or os.environ.get("AUTH_SC002A_FULL") == "1"
    rounds = 100 if full else 5
    user = account_factory.create_active()

    for round_i in range(rounds):
        # Age prior challenges so a new request is allowed.
        engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE verification_challenges "
                        "SET created_at = NOW() - INTERVAL '61 seconds', "
                        "state = CASE WHEN state IN ('pending_delivery','delivered') "
                        "THEN 'superseded' ELSE state END "
                        "WHERE user_id = CAST(:uid AS uuid)"
                    ),
                    {"uid": str(user.id)},
                )
        finally:
            engine.dispose()

        cid_a, code_a = _request_delivered_challenge(
            conc_client, auth_migrated_postgres, user.phone_normalized
        )
        ra = conc_client.post(
            "/api/v1/auth/sessions",
            json={"challenge_id": cid_a, "code": code_a},
            headers={"Origin": ORIGIN},
        )
        assert ra.status_code == 200, ra.text
        cookie_a = ra.headers.get("set-cookie", "")
        assert SESSION_COOKIE_NAME in cookie_a

        engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE verification_challenges "
                        "SET created_at = NOW() - INTERVAL '61 seconds' "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": cid_a},
                )
        finally:
            engine.dispose()

        cid_b, code_b = _request_delivered_challenge(
            conc_client, auth_migrated_postgres, user.phone_normalized
        )
        rb = conc_client.post(
            "/api/v1/auth/sessions",
            json={"challenge_id": cid_b, "code": code_b},
            headers={"Origin": ORIGIN},
        )
        assert rb.status_code == 200, rb.text

        engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                active = conn.execute(
                    text(
                        "SELECT count(*) FROM auth_sessions "
                        "WHERE user_id = CAST(:uid AS uuid) AND revoked_at IS NULL"
                    ),
                    {"uid": str(user.id)},
                ).scalar_one()
                assert int(active) == 1, f"round {round_i} active={active}"
        finally:
            engine.dispose()

        # Old session rejected within 1s (FR-015).
        deadline = time_mod.monotonic() + 1.0
        rejected = False
        while time_mod.monotonic() <= deadline:
            get_res = conc_client.get(
                "/api/v1/auth/session",
                headers={"Cookie": cookie_a.split(";")[0]},
            )
            if get_res.status_code in (401, 404):
                if get_res.status_code == 401:
                    assert get_res.json().get("code") == "UNAUTHENTICATED"
                rejected = True
                break
            time_mod.sleep(0.05)
        assert rejected, f"round {round_i}: old cookie still accepted after 1s"
