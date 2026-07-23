"""DB unavailable and envelope dependency failures (T071 / T076)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import MemoryRateLimiter
from tests.integration.conftest_register import unique_phone

pytestmark = pytest.mark.integration


def test_register_without_database_uses_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        client.app.state.session_factory = None
        r = client.post(
            "/api/v1/auth/register",
            json={"phone": unique_phone(), "nickname": "无库", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 503
        body = r.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert "request_id" in body
        assert "timestamp" in body
        assert "detail" not in body


def test_register_missing_idempotency_key(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        r = client.post(
            "/api/v1/auth/register",
            json={"phone": unique_phone(), "nickname": "无键", "role": "buyer"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
