"""Concurrent registration of the same phone (T069 / SC-002)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import create_session_engine
from app.domain.users.models import User
from app.domain.users.service import RegistrationService
from tests.integration.conftest_register import unique_phone

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_hundred_concurrent_same_phone_one_user(
    migrated_postgres: str,
) -> None:
    phone = unique_phone()
    engine = create_session_engine(migrated_postgres)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def one_attempt(i: int) -> str:
        async with factory() as session:
            svc = RegistrationService(session)
            result = await svc.register(
                phone=phone,
                nickname=f"c{i}",
                role="buyer",
                idempotency_key=str(uuid.uuid4()),
            )
            return result.code

    codes = await asyncio.gather(*[one_attempt(i) for i in range(100)])
    successes = [c for c in codes if c == "0"]
    assert len(successes) == 1, codes[:20]

    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.phone_normalized == phone)
        )
        assert count == 1

    await engine.dispose()
