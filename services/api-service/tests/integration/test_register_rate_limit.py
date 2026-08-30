"""HTTP rate limiting and anti-enumeration (T070).

Public POST /register is a closed gate (AUTH_VERIFICATION_REQUIRED) and must
not leak occupancy via 200/409/429 variance. Profile-completion still applies
the generic IP limiter.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import MemoryRateLimiter
from tests.integration.conftest_register import unique_phone

pytestmark = pytest.mark.integration

ORIGIN = "https://127.0.0.1:5173"


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


def test_public_register_uniform_reject_ignores_limiter(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(ip_limit=0, phone_limit=0)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        bodies = []
        for phone in ("not-a-phone", unique_phone(), "13800138000"):
            r = client.post(
                "/api/v1/auth/register",
                json={"phone": phone, "nickname": "枚举", "role": "buyer"},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 403
            b = r.json()
            assert b["code"] == "AUTH_VERIFICATION_REQUIRED"
            bodies.append((b["code"], b["message"], tuple(sorted(b.keys()))))
        assert len(set(bodies)) == 1
        assert (
            "RATE_LIMITED"
            not in client.post(
                "/api/v1/auth/register",
                json={"phone": unique_phone(), "nickname": "枚举", "role": "buyer"},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            ).text
        )
    finally:
        client.__exit__(None, None, None)


def test_profile_completion_ip_rate_limit(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(ip_limit=2, phone_limit=100)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        for _ in range(2):
            r = client.post(
                "/api/v1/auth/profile-completions",
                json={"nickname": "限流", "role": "buyer"},
                headers={
                    "Origin": ORIGIN,
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            assert r.status_code == 401
            assert r.json()["code"] == "AUTH_VERIFICATION_REQUIRED"
        limited = client.post(
            "/api/v1/auth/profile-completions",
            json={"nickname": "限流", "role": "buyer"},
            headers={
                "Origin": ORIGIN,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        assert limited.status_code == 429
        body = limited.json()
        assert body["code"] == "RATE_LIMITED"
        assert "request_id" in body
        assert "timestamp" in body
        assert set(body.keys()) >= {"code", "message", "request_id", "timestamp"}
    finally:
        client.__exit__(None, None, None)


def test_profile_completion_redis_fail_closed_503(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = MemoryRateLimiter(fail=True)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        r = client.post(
            "/api/v1/auth/profile-completions",
            json={"nickname": "x", "role": "buyer"},
            headers={
                "Origin": ORIGIN,
                "Idempotency-Key": str(uuid.uuid4()),
            },
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
    """RATE_LIMITED envelope shape must not vary by nickname/role on complete."""
    limiter = MemoryRateLimiter(ip_limit=0, phone_limit=0)
    client = _client(migrated_postgres, monkeypatch, limiter)
    try:
        bodies = []
        for nick in ("枚举", "another", "x"):
            r = client.post(
                "/api/v1/auth/profile-completions",
                json={"nickname": nick, "role": "buyer"},
                headers={
                    "Origin": ORIGIN,
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            assert r.status_code == 429
            b = r.json()
            bodies.append((b["code"], b["message"], tuple(sorted(b.keys()))))
        assert len(set(bodies)) == 1
    finally:
        client.__exit__(None, None, None)
