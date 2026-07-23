"""RegistrationService domain tests against real disposable PostgreSQL (T068)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import create_session_engine
from app.domain.users.models import RegistrationIdempotencyRecord, User
from app.domain.users.service import RegistrationService
from tests.conftest import PostgresHandle
from tests.integration.conftest_register import run_alembic, unique_phone

pytestmark = pytest.mark.integration


@pytest.fixture
async def session(postgres_container: PostgresHandle) -> AsyncSession:
    url = postgres_container.database_url()
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_happy_path(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    key = str(uuid.uuid4())
    result = await svc.register(
        phone=phone, nickname="测用户", role="buyer", idempotency_key=key
    )
    assert result.kind == "success"
    assert result.data["role"] == "buyer"
    assert result.data["status"] == "active"
    assert "user_id" in result.data
    assert phone not in str(result.data)


@pytest.mark.asyncio
async def test_validation_errors(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    result = await svc.register(
        phone="bad", nickname="", role="buyer", idempotency_key=str(uuid.uuid4())
    )
    assert result.kind == "validation"
    assert result.code == "VALIDATION_ERROR"
    assert "phone" in result.data["errors"]


@pytest.mark.asyncio
async def test_phone_already_registered(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    await svc.register(
        phone=phone, nickname="a", role="seller", idempotency_key=str(uuid.uuid4())
    )
    again = await svc.register(
        phone=phone, nickname="b", role="buyer", idempotency_key=str(uuid.uuid4())
    )
    assert again.kind == "phone_taken"
    assert again.code == "PHONE_ALREADY_REGISTERED"
    assert "nickname" not in (again.message or "").lower()


@pytest.mark.asyncio
async def test_soft_deleted_account_unavailable(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    first = await svc.register(
        phone=phone, nickname="a", role="both", idempotency_key=str(uuid.uuid4())
    )
    assert first.kind == "success"
    await session.execute(
        update(User)
        .where(User.phone_normalized == phone)
        .values(is_deleted=True)
    )
    await session.commit()
    again = await svc.register(
        phone=phone, nickname="z", role="buyer", idempotency_key=str(uuid.uuid4())
    )
    assert again.kind == "account_unavailable"
    assert again.code == "ACCOUNT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_idempotency_replay(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    key = str(uuid.uuid4())
    first = await svc.register(
        phone=phone, nickname="同", role="buyer", idempotency_key=key
    )
    second = await svc.register(
        phone=phone, nickname="同", role="buyer", idempotency_key=key
    )
    assert first.kind == "success" and second.kind == "success"
    assert first.data["user_id"] == second.data["user_id"]
    rows = await session.execute(select(User).where(User.phone_normalized == phone))
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_idempotency_conflict_different_body(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    key = str(uuid.uuid4())
    await svc.register(
        phone=phone, nickname="同", role="buyer", idempotency_key=key
    )
    conflict = await svc.register(
        phone=phone, nickname="不同", role="buyer", idempotency_key=key
    )
    assert conflict.kind == "idempotency_conflict"
    assert conflict.code == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_idempotency_expired(session: AsyncSession) -> None:
    svc = RegistrationService(session)
    phone = unique_phone()
    key = str(uuid.uuid4())
    first = await svc.register(
        phone=phone, nickname="过期", role="buyer", idempotency_key=key
    )
    assert first.kind == "success"
    past = datetime.now(timezone.utc) - timedelta(hours=25)
    await session.execute(
        update(RegistrationIdempotencyRecord)
        .where(RegistrationIdempotencyRecord.idempotency_key == key)
        .values(expires_at=past, created_at=past)
    )
    await session.commit()
    expired = await svc.register(
        phone=phone, nickname="过期", role="buyer", idempotency_key=key
    )
    assert expired.kind == "idempotency_expired"
    assert expired.code == "IDEMPOTENCY_KEY_EXPIRED"
