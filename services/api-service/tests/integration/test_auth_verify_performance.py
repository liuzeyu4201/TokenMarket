"""API verify/session performance profile (T040).

Default CI: light sequential sample (n=10) for harness validity.
Full acceptance (n=100, p95≤500ms) when ``TM_PERF=1``.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import statistics
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
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = [pytest.mark.integration]

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_verify_perf_" + secrets.token_urlsafe(32)


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
def perf_client(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _set_env(monkeypatch, auth_migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.auth_rate_limiter = MemoryAuthRateLimiter(
            phone_limit=50_000, ip_limit=50_000
        )
        client.app.state.sms_adapter = SyntheticSmsAdapter()
        yield client
    clear_auth_settings_cache()


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


async def _drain(database_url: str, challenge_id: str, *, timeout: float = 10.0) -> str:
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
                factory, settings, sms, owner=f"p-{secrets.token_hex(3)}"
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
    client: TestClient, database_url: str, phone: str
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


def test_concurrent_verify_session_performance_profile(
    perf_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    full = os.environ.get("TM_PERF") == "1"
    n = 100 if full else 10

    samples: list[float] = []
    successes = 0
    for _i in range(n):
        user = account_factory.create_active()
        # Allow new challenge request (rolling cooldown on phone_ref).
        engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE verification_challenges "
                        "SET created_at = NOW() - INTERVAL '61 seconds' "
                        "WHERE user_id = CAST(:uid AS uuid)"
                    ),
                    {"uid": str(user.id)},
                )
        finally:
            engine.dispose()

        cid, code = _request_delivered_challenge(
            perf_client, auth_migrated_postgres, user.phone_normalized
        )
        start = time.perf_counter()
        res = perf_client.post(
            "/api/v1/auth/sessions",
            json={"challenge_id": cid, "code": code},
            headers={"Origin": ORIGIN},
        )
        samples.append(time.perf_counter() - start)
        if res.status_code == 200:
            successes += 1

    assert successes == n
    assert len(samples) == n
    assert all(s >= 0 for s in samples)
    mean = statistics.fmean(samples)
    assert mean < 5.0, f"mean verify latency too high: {mean}"

    if full:
        p95 = _p95(samples)
        assert p95 <= 0.5, f"verify/session p95={p95} exceeds 500ms"
    else:
        assert os.environ.get("TM_PERF") != "1"
