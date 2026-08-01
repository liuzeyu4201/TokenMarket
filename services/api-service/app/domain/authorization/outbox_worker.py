"""Optional outbox publisher for authorization audit events.

V0.1 primary path writes security events synchronously. This worker can
drain pending outbox rows if producers use outbox-only inserts later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.authorization.models import (
    AuthorizationAuditOutbox,
    AuthorizationSecurityEvent,
)

logger = logging.getLogger("api-service")


async def publish_pending_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = 100,
) -> int:
    """Publish up to batch_size pending outbox rows. Returns published count."""
    published = 0
    async with session_factory() as session:
        stmt = (
            select(AuthorizationAuditOutbox)
            .where(
                AuthorizationAuditOutbox.state == "pending",
                AuthorizationAuditOutbox.available_at <= datetime.now(timezone.utc),
            )
            .order_by(AuthorizationAuditOutbox.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            payload: dict[str, Any] = dict(row.payload)
            event = AuthorizationSecurityEvent(
                event_type=payload["event_type"],
                outcome=payload["outcome"],
                reason_code=payload["reason_code"],
                action=payload["action"],
                policy_version=payload["policy_version"],
                actor_user_id=_maybe_uuid(payload.get("actor_user_id")),
                session_id=_maybe_uuid(payload.get("session_id")),
                resource_type=payload.get("resource_type"),
                resource_id=_maybe_uuid(payload.get("resource_id")),
                request_id=payload["request_id"],
                safe_metadata=payload.get("safe_metadata") or {},
                delete_after=_maybe_dt(payload["delete_after"]),
            )
            session.add(event)
            await session.flush()
            row.state = "published"
            row.published_event_id = event.id
            row.updated_at = datetime.now(timezone.utc)
            published += 1
        await session.commit()
    return published


def _maybe_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _maybe_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
