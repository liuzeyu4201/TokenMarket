"""HTTP conflict paths: occupied phone and soft-delete (T068 companion)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import create_session_engine
from app.domain.users.models import User
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


def test_http_phone_already_registered(client: TestClient) -> None:
    phone = unique_phone()
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    r1 = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "一", "role": "buyer"},
        headers=headers,
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "nickname": "二", "role": "seller"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r2.status_code == 409
    body = r2.json()
    assert body["code"] == "PHONE_ALREADY_REGISTERED"
    assert "一" not in r2.text
    assert "request_id" in body


@pytest.mark.asyncio
async def test_http_soft_deleted_unavailable(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    monkeypatch.delenv("REDIS_URL", raising=False)
    phone = unique_phone()
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        r1 = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "nickname": "软删", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r1.status_code == 200

    engine = create_session_engine(migrated_postgres)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            update(User).where(User.phone_normalized == phone).values(is_deleted=True)
        )
        await session.commit()
    await engine.dispose()

    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        r2 = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "nickname": "再来", "role": "buyer"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r2.status_code == 409
        assert r2.json()["code"] == "ACCOUNT_UNAVAILABLE"
        assert "软删" not in r2.text
