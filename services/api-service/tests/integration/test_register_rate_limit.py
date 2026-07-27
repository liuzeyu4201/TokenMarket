"""HTTP rate limiting and anti-enumeration (T070)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import MemoryRateLimiter
from tests.integration.conftest_register import unique_phone

pytestmark = pytest.mark.integration


def _client(
    url: str, monkeypatch: pytest.MonkeyPatch, limiter: MemoryRateLimiter
) -> TestClient:
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("REDIS_URL", raising=False)
    client = TestClient(app)
    client.__enter__()
    client.app.state.rate_limiter = limiter
    return client


def test_ip_rate_limit_and_uniform_body(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(ip_limit=2, phone_limit=100)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        for _ in range(2):
            r = client.post(
                "/api/v1/auth/register",
                json={
                    "phone": unique_phone(),
                    "nickname": "限流",
                    "role": "buyer",
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code in (200, 400)
        limited = client.post(
            "/api/v1/auth/register",
            json={"phone": unique_phone(), "nickname": "限流", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert limited.status_code == 429
        body = limited.json()
        assert body["code"] == "RATE_LIMITED"
        assert "request_id" in body
        assert "timestamp" in body
        assert set(body.keys()) >= {"code", "message", "request_id", "timestamp"}
    finally:
        client.__exit__(None, None, None)


def test_phone_rate_limit(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(ip_limit=1000, phone_limit=1)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        phone = unique_phone()
        r1 = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "nickname": "p1", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "nickname": "p2", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        # second attempt counts phone bucket → rate limited before conflict
        assert r2.status_code == 429
        assert r2.json()["code"] == "RATE_LIMITED"
    finally:
        client.__exit__(None, None, None)


def test_redis_fail_closed_503(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(fail=True)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        r = client.post(
            "/api/v1/auth/register",
            json={"phone": unique_phone(), "nickname": "x", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 503
        body = r.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert "request_id" in body
    finally:
        client.__exit__(None, None, None)


def test_anti_enumeration_rate_limit_shape(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RATE_LIMITED envelope shape must not vary by phone legitimacy/occupancy."""
    limiter = MemoryRateLimiter(ip_limit=0, phone_limit=0)  # immediate limit
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        bodies = []
        for phone in ("not-a-phone", unique_phone(), "13800138000"):
            r = client.post(
                "/api/v1/auth/register",
                json={"phone": phone, "nickname": "枚举", "role": "buyer"},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 429
            b = r.json()
            bodies.append((b["code"], b["message"], tuple(sorted(b.keys()))))
        assert len(set(bodies)) == 1
    finally:
        client.__exit__(None, None, None)
