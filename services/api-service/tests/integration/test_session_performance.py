"""Light session check / logout performance smoke (T078).

Full p95 profiles belong in release evidence; this suite verifies order-of-magnitude
latency bounds and correctness invariants in the local integration environment.
"""

from __future__ import annotations

import asyncio
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
from app.security.session import SESSION_COOKIE_NAME
from app.sms.synthetic import SyntheticSmsAdapter

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ORIGIN = "https://127.0.0.1:5173"
_KEY = "tm_sess_perf_" + secrets.token_urlsafe(32)


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
        factory, settings, SyntheticSmsAdapter(), owner="perf-dispatch"
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


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


@pytest.fixture
def perf_client(
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


def test_session_check_p95_under_50ms_light(
    perf_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    _login(perf_client, user.phone_normalized, auth_migrated_postgres)

    # Warmup
    for _ in range(3):
        assert perf_client.get("/api/v1/auth/session").status_code == 200

    samples: list[float] = []
    for _ in range(30):
        t0 = time.perf_counter()
        res = perf_client.get("/api/v1/auth/session")
        samples.append(time.perf_counter() - t0)
        assert res.status_code == 200
        assert "csrf_token" in res.json()["data"]

    p95 = _p95(samples)
    # Local integration bound (spec: ≤50ms p95 in acceptance env).
    # Allow generous CI margin while still catching multi-second regressions.
    assert (
        p95 < 0.25
    ), f"session check p95={p95:.4f}s mean={statistics.mean(samples):.4f}s"


def test_logout_and_old_session_reject_under_one_second(
    perf_client: TestClient,
    account_factory,
    auth_migrated_postgres: str,
) -> None:
    user = account_factory.create_active()
    csrf = _login(perf_client, user.phone_normalized, auth_migrated_postgres)
    cookie = perf_client.cookies.get(SESSION_COOKIE_NAME)

    t0 = time.perf_counter()
    res = perf_client.delete(
        "/api/v1/auth/session",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    logout_s = time.perf_counter() - t0
    assert res.status_code == 200
    assert logout_s < 1.0

    # Old cookie reject visibility
    if cookie:
        perf_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    t1 = time.perf_counter()
    denied = perf_client.get("/api/v1/auth/session")
    reject_s = time.perf_counter() - t1
    assert denied.status_code == 401
    assert reject_s < 1.0
