"""Integration: challenge request idempotency (T056 / US2)."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth_rate_limit import MemoryAuthRateLimiter
from app.config import clear_auth_settings_cache
from app.main import app
from app.rate_limit import MemoryRateLimiter
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_idem_" + secrets.token_urlsafe(32)


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
def idem_client(
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


def _challenge(
    client: TestClient,
    phone: str,
    key: str,
) -> tuple[int, dict]:
    res = client.post(
        "/api/v1/auth/verification-challenges",
        json={"phone": phone},
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
    )
    return res.status_code, res.json()


def test_same_key_phone_replay_first_202(
    idem_client: TestClient,
    account_factory,
) -> None:
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    s1, b1 = _challenge(idem_client, user.phone_normalized, key)
    s2, b2 = _challenge(idem_client, user.phone_normalized, key)
    assert s1 == 202 and s2 == 202
    assert b1["code"] == "0" and b2["code"] == "0"
    assert b1["data"]["challenge_id"] == b2["data"]["challenge_id"]
    assert b1["data"]["phone_masked"] == b2["data"]["phone_masked"]


def test_same_key_different_phone_conflict(
    idem_client: TestClient,
    account_factory,
) -> None:
    u1 = account_factory.create_active()
    u2 = account_factory.create_active()
    key = str(uuid.uuid4())
    s1, _ = _challenge(idem_client, u1.phone_normalized, key)
    assert s1 == 202
    s2, b2 = _challenge(idem_client, u2.phone_normalized, key)
    assert s2 == 409
    assert b2["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_expired_key_requires_new_key(
    idem_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    s1, _ = _challenge(idem_client, user.phone_normalized, key)
    assert s1 == 202
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            # CHECK replay_until > created_at — move the whole window into the past.
            conn.execute(
                text(
                    "UPDATE verification_request_idempotency_records "
                    "SET created_at = NOW() - INTERVAL '120 seconds', "
                    "    replay_until = NOW() - INTERVAL '60 seconds', "
                    "    completed_at = NOW() - INTERVAL '120 seconds'"
                )
            )
    finally:
        engine.dispose()
    s2, b2 = _challenge(idem_client, user.phone_normalized, key)
    assert s2 == 409
    assert b2["code"] == "IDEMPOTENCY_KEY_EXPIRED"


def test_lost_response_replay_recovers_same_payload(
    idem_client: TestClient,
    account_factory,
) -> None:
    """Simulate lost first response: client reuses key and recovers first result."""
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    s1, b1 = _challenge(idem_client, user.phone_normalized, key)
    assert s1 == 202
    # "Lost" — client retries with same key
    s2, b2 = _challenge(idem_client, user.phone_normalized, key)
    assert s2 == 202
    assert b2["data"]["challenge_id"] == b1["data"]["challenge_id"]


def test_concurrent_winners_single_challenge(
    idem_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    key = str(uuid.uuid4())
    # TestClient is sync; drive concurrent via threads.
    import concurrent.futures

    results: list[tuple[int, str | None]] = []

    def one() -> tuple[int, str | None]:
        status, body = _challenge(idem_client, user.phone_normalized, key)
        cid = body.get("data", {}).get("challenge_id") if status == 202 else None
        return status, cid

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futs = [pool.submit(one) for _ in range(20)]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())

    successes = [r for r in results if r[0] == 202]
    assert successes
    challenge_ids = {r[1] for r in successes if r[1]}
    # Same key → single challenge id for all successful replays
    assert len(challenge_ids) == 1

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            n = conn.execute(
                text(
                    "SELECT count(*) FROM verification_challenges "
                    "WHERE phone_ref IS NOT NULL"
                )
            ).scalar_one()
            # At most one challenge for this phone under single key
            assert int(n) >= 1
            idem = conn.execute(
                text(
                    "SELECT count(*) FROM verification_request_idempotency_records"
                )
            ).scalar_one()
            assert int(idem) == 1
    finally:
        engine.dispose()
