"""Audit persist failure must not return naked business deny."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.domain.authorization.matrix import Action
from app.domain.authorization.service import AuthorizationService
from app.domain.users.models import UserRole, UserStatus


@pytest.mark.asyncio
async def test_deny_without_audit_persist_returns_503() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
    )
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.insert_security_event = AsyncMock(
        side_effect=OperationalError("stmt", {}, Exception("down"))
    )
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_register,
        request_id="fail-audit",
    )
    assert d.http_status == 503
    assert d.code == "SERVICE_UNAVAILABLE"
    assert d.code != "FORBIDDEN_ROLE"
