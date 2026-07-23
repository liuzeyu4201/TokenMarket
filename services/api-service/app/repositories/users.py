"""User repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import User, UserRole, UserStatus


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_phone(self, phone_normalized: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.phone_normalized == phone_normalized)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        phone_normalized: str,
        nickname: str,
        role: UserRole,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            phone_normalized=phone_normalized,
            nickname=nickname,
            role=role,
            status=UserStatus.active,
            is_deleted=False,
            version=1,
        )
        self._session.add(user)
        await self._session.flush()
        return user
