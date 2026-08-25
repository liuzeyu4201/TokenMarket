"""Authorization repository: ownership, events, outbox."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.authorization.models import (
    AuthorizationAuditOutbox,
    AuthorizationSecurityEvent,
    ResourceOwnership,
)
from app.domain.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_ownership(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> ResourceOwnership | None:
        stmt = select(ResourceOwnership).where(
            ResourceOwnership.resource_type == resource_type,
            ResourceOwnership.resource_id == resource_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_ownership(
        self,
        *,
        resource_type: str,
        resource_id: uuid.UUID | None,
        owner_user_id: uuid.UUID,
        request_id: str,
        lifecycle_status: str = "active",
    ) -> ResourceOwnership:
        rid = resource_id or uuid.uuid4()
        row = ResourceOwnership(
            resource_type=resource_type,
            resource_id=rid,
            owner_user_id=owner_user_id,
            lifecycle_status=lifecycle_status,
            created_request_id=request_id,
            version=1,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_ownership_status(
        self,
        row: ResourceOwnership,
        *,
        lifecycle_status: str,
    ) -> ResourceOwnership:
        row.lifecycle_status = lifecycle_status
        row.version = int(row.version) + 1
        row.updated_at = utc_now()
        await self._session.flush()
        return row

    async def insert_security_event(
        self, payload: dict[str, Any]
    ) -> AuthorizationSecurityEvent:
        event = AuthorizationSecurityEvent(
            event_type=payload["event_type"],
            outcome=payload["outcome"],
            reason_code=payload["reason_code"],
            action=payload["action"],
            policy_version=payload["policy_version"],
            actor_user_id=payload.get("actor_user_id"),
            session_id=payload.get("session_id"),
            resource_type=payload.get("resource_type"),
            resource_id=payload.get("resource_id"),
            request_id=payload["request_id"],
            safe_metadata=payload.get("safe_metadata") or {},
            delete_after=payload["delete_after"],
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def insert_outbox(
        self, *, request_id: str, payload: dict[str, Any], delete_after: datetime
    ) -> AuthorizationAuditOutbox:
        # JSONB-safe payload (UUID/datetime as strings)
        safe = _jsonable(payload)
        row = AuthorizationAuditOutbox(
            payload=safe,
            request_id=request_id,
            state="pending",
            attempts=0,
            available_at=utc_now(),
            delete_after=delete_after,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
