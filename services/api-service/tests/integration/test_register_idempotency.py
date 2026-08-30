"""HTTP idempotency replay and conflict (T068)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import MemoryRateLimiter
from tests.integration.conftest_register import unique_phone

pytestmark = pytest.mark.integration


@pytest.fixture
def client(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(app) as c:
        c.app.state.rate_limiter = MemoryRateLimiter()
        yield c


def test_idempotent_replay_same_key_body(client: TestClient) -> None:
    phone = unique_phone()
    key = str(uuid.uuid4())
    body = {"phone": phone, "nickname": "幂等", "role": "buyer"}
    r1 = client.post(
        "/api/v1/auth/register", json=body, headers={"Idempotency-Key": key}
    )
    r2 = client.post(
        "/api/v1/auth/register", json=body, headers={"Idempotency-Key": key}
    )
    assert r1.status_code == 403 and r2.status_code == 403
    assert r1.json()["code"] == r2.json()["code"] == "AUTH_VERIFICATION_REQUIRED"


def test_idempotent_conflict_different_body(client: TestClient) -> None:
    phone = unique_phone()
    key = str(uuid.uuid4())
    client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "甲", "role": "buyer"},
        headers={"Idempotency-Key": key},
    )
    r = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "乙", "role": "buyer"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "AUTH_VERIFICATION_REQUIRED"
    assert "IDEMPOTENCY_KEY_CONFLICT" not in r.text
