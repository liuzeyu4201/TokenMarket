"""Registration idempotency repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import RegistrationIdempotencyRecord

IDEMPOTENCY_TTL = timedelta(hours=24)


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> RegistrationIdempotencyRecord | None:
        result = await self._session.execute(
            select(RegistrationIdempotencyRecord).where(
                RegistrationIdempotencyRecord.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        key: str,
        request_hash: str,
        user_id: uuid.UUID,
        result_code: str,
        result_payload: dict[str, Any],
    ) -> RegistrationIdempotencyRecord:
        now = datetime.now(timezone.utc)
        rec = RegistrationIdempotencyRecord(
            id=uuid.uuid4(),
            idempotency_key=key,
            request_hash=request_hash,
            user_id=user_id,
            result_code=result_code,
            result_payload=result_payload,
            created_at=now,
            expires_at=now + IDEMPOTENCY_TTL,
        )
        self._session.add(rec)
        await self._session.flush()
        return rec
