"""Unit tests for authorization audit outbox worker."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.outbox_worker import publish_pending_batch


@pytest.mark.asyncio
async def test_publish_empty_batch() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    factory = MagicMock()
    # async with factory() as session
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm

    n = await publish_pending_batch(factory, batch_size=10)
    assert n == 0
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_publish_one_row() -> None:
    now = datetime.now(timezone.utc)
    row = MagicMock()
    row.payload = {
        "event_type": "authz.role_denied",
        "outcome": "denied",
        "reason_code": "ROLE_DENIED",
        "action": "seller_key.register",
        "policy_version": "authz-matrix-v1",
        "actor_user_id": str(uuid.uuid4()),
        "session_id": None,
        "resource_type": None,
        "resource_id": None,
        "request_id": "r1",
        "safe_metadata": {},
        "delete_after": (now + timedelta(days=90)).isoformat(),
    }
    row.state = "pending"
    row.published_event_id = None

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm

    n = await publish_pending_batch(factory, batch_size=5)
    assert n == 1
    assert row.state == "published"
    session.add.assert_called()
    session.commit.assert_awaited()
