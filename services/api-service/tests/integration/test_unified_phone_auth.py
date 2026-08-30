"""Integration: unified OTP register/login (SF06)."""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache, load_auth_settings
from app.dependencies import create_session_engine
from app.dispatch.auth_delivery import AuthDeliveryDispatcher
from app.domain.authentication.profile_service import ProfileCompletionService
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.security.otp import derive_otp
from app.security.profile_token import PROFILE_COOKIE_NAME
from app.security.session import SESSION_COOKIE_NAME
from app.sms.synthetic import SyntheticSmsAdapter
from tests.integration.conftest_register import run_alembic

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_unified_" + secrets.token_urlsafe(32)


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
def unified_client(
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


def _phone() -> str:
    return f"139{uuid.uuid4().int % 10**8:08d}"[:11]


def _profile_cookie_header(res) -> str:
    for v in res.headers.get_list("set-cookie"):
        if v.startswith(PROFILE_COOKIE_NAME + "="):
            return v.split(";", 1)[0]
    raise AssertionError("missing profile cookie")


def _profile_cookie_value(res) -> str:
    header = _profile_cookie_header(res)
    return header.split("=", 1)[1]


async def _drain(database_url: str, challenge_id: str) -> None:
    engine_sync = create_engine(database_url, pool_pre_ping=True)
    sms = SyntheticSmsAdapter()
    for _ in range(8):
        async_engine = create_session_engine(database_url)
        factory = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )
        dispatcher = AuthDeliveryDispatcher(
            factory, load_auth_settings(), sms, owner=f"u-{secrets.token_hex(3)}"
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
            engine_sync.dispose()
            return
        await asyncio.sleep(0.05)
    engine_sync.dispose()
    raise AssertionError("challenge not delivered")


def _verify_unknown(
    client: TestClient, database_url: str, phone: str
) -> tuple[str, str]:
    ch = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert ch.status_code == 202, ch.text
    challenge_id = ch.json()["data"]["challenge_id"]
    asyncio.run(_drain(database_url, challenge_id))
    otp_key = load_auth_settings().key_material("otp").current
    code = derive_otp(otp_key, challenge_id)
    res = client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert res.status_code == 200, res.text
    assert res.json()["code"] == "PROFILE_COMPLETION_REQUIRED"
    return code, _profile_cookie_value(res)


def test_unknown_and_known_challenge_shape_match(
    unified_client: TestClient,
    account_factory,
) -> None:
    known = account_factory.create_active()
    unknown = _phone()
    a = unified_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": known.phone_normalized},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    b = unified_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": unknown},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert a.status_code == b.status_code == 202
    assert set(a.json().keys()) == set(b.json().keys())
    assert a.json()["code"] == b.json()["code"] == "0"
    assert set(a.json()["data"].keys()) == set(b.json()["data"].keys())


def test_otp_without_profile_creates_no_user(
    unified_client: TestClient,
    auth_migrated_postgres: str,
) -> None:
    phone = _phone()
    _verify_unknown(unified_client, auth_migrated_postgres, phone)
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM users WHERE phone_normalized = :p"),
            {"p": phone},
        ).scalar_one()
    engine.dispose()
    assert n == 0


def test_complete_profile_creates_user_and_session(
    unified_client: TestClient,
    auth_migrated_postgres: str,
) -> None:
    phone = _phone()
    _, cookie_value = _verify_unknown(unified_client, auth_migrated_postgres, phone)
    done = unified_client.post(
        "/api/v1/auth/profile-completions",
        json={"nickname": "新买家", "role": "buyer"},
        headers={
            "Origin": ORIGIN,
            "Idempotency-Key": str(uuid.uuid4()),
            "Cookie": f"{PROFILE_COOKIE_NAME}={cookie_value}",
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["code"] == "0"
    assert done.json()["data"]["role"] == "buyer"
    set_cookie = done.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie or done.cookies.get(SESSION_COOKIE_NAME)
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM users WHERE phone_normalized = :p"),
            {"p": phone},
        ).scalar_one()
    engine.dispose()
    assert n == 1


def test_replay_otp_does_not_issue_second_intent(
    unified_client: TestClient,
    auth_migrated_postgres: str,
) -> None:
    phone = _phone()
    ch = unified_client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid.uuid4())},
    )
    challenge_id = ch.json()["data"]["challenge_id"]
    asyncio.run(_drain(auth_migrated_postgres, challenge_id))
    otp_key = load_auth_settings().key_material("otp").current
    code = derive_otp(otp_key, challenge_id)
    first = unified_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert first.json()["code"] == "PROFILE_COMPLETION_REQUIRED"
    second = unified_client.post(
        "/api/v1/auth/sessions",
        json={"challenge_id": challenge_id, "code": code},
        headers={"Origin": ORIGIN},
    )
    assert second.status_code in (401, 409)
    assert second.json()["code"] != "0"


def test_expired_profile_cookie_creates_no_user(
    unified_client: TestClient,
    auth_migrated_postgres: str,
) -> None:
    phone = _phone()
    _, cookie_value = _verify_unknown(unified_client, auth_migrated_postgres, phone)
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE profile_completion_intents "
                "SET created_at = NOW() - INTERVAL '2 minutes', "
                "    expires_at = NOW() - INTERVAL '1 second' "
                "WHERE consumed_at IS NULL"
            )
        )
    done = unified_client.post(
        "/api/v1/auth/profile-completions",
        json={"nickname": "过期", "role": "buyer"},
        headers={
            "Origin": ORIGIN,
            "Idempotency-Key": str(uuid.uuid4()),
            "Cookie": f"{PROFILE_COOKIE_NAME}={cookie_value}",
        },
    )
    assert done.status_code == 401, done.text
    assert done.json()["code"] == "PROFILE_EXPIRED"
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM users WHERE phone_normalized = :p"),
            {"p": phone},
        ).scalar_one()
    engine.dispose()
    assert n == 0


def test_fifty_concurrent_completions_one_user(
    unified_client: TestClient,
    auth_migrated_postgres: str,
) -> None:
    phone = _phone()
    _, cookie_value = _verify_unknown(unified_client, auth_migrated_postgres, phone)
    settings = load_auth_settings()

    async def _run() -> list[str]:
        engine = create_session_engine(auth_migrated_postgres)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async def one_attempt(i: int) -> str:
            async with factory() as session:
                svc = ProfileCompletionService(session, settings)
                result = await svc.complete(
                    cookie_value=cookie_value,
                    nickname=f"并发{i}",
                    role="buyer",
                    idempotency_key=str(uuid.uuid4()),
                    request_id=f"pci-{i}",
                )
                return result.code

        codes = await asyncio.gather(*[one_attempt(i) for i in range(50)])
        await engine.dispose()
        return list(codes)

    codes = asyncio.run(_run())
    successes = [c for c in codes if c == "0"]
    assert len(successes) == 1, codes[:20]
    for c in codes:
        assert c in (
            "0",
            "PROFILE_EXPIRED",
            "PHONE_ALREADY_REGISTERED",
            "AUTH_VERIFICATION_REQUIRED",
        )
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM users WHERE phone_normalized = :p"),
            {"p": phone},
        ).scalar_one()
        sessions = conn.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()
    engine.dispose()
    assert n == 1
    assert sessions == 1


def test_logs_do_not_contain_plaintext_otp(
    unified_client: TestClient,
    auth_migrated_postgres: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    phone = _phone()
    with caplog.at_level(logging.DEBUG, logger="api-service"):
        code, cookie_value = _verify_unknown(
            unified_client, auth_migrated_postgres, phone
        )
        unified_client.post(
            "/api/v1/auth/profile-completions",
            json={"nickname": "日志", "role": "buyer"},
            headers={
                "Origin": ORIGIN,
                "Idempotency-Key": str(uuid.uuid4()),
                "Cookie": f"{PROFILE_COOKIE_NAME}={cookie_value}",
            },
        )
    assert code not in caplog.text
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    with engine.connect() as conn:
        events = conn.execute(
            text(
                "SELECT event_type, reason_code, "
                "coalesce(safe_metadata::text, '') "
                "FROM authentication_security_events"
            )
        ).fetchall()
        digest_null = conn.execute(
            text(
                "SELECT code_digest IS NULL FROM verification_challenges "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar_one()
    engine.dispose()
    blob = " ".join(" ".join(str(x) for x in row) for row in events)
    assert code not in blob
    assert digest_null is True


def test_0008_upgrade_downgrade_roundtrip(auth_migrated_postgres: str) -> None:
    down = run_alembic(
        auth_migrated_postgres, "downgrade", "0007_actor_scoped_idempotency"
    )
    assert down.returncode == 0, down.stdout + down.stderr
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        insp = inspect(engine)
        assert "profile_completion_intents" not in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("verification_challenges")}
        assert "phone_normalized" not in cols
    finally:
        engine.dispose()
    up = run_alembic(auth_migrated_postgres, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        insp = inspect(engine)
        assert "profile_completion_intents" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("verification_challenges")}
        assert "phone_normalized" in cols
    finally:
        engine.dispose()
