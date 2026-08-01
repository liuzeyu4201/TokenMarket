"""Client-supplied identity fields must not elevate privileges."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.matrix import Action
from app.domain.authorization.service import AuthorizationService
from app.domain.users.models import UserRole, UserStatus


@pytest.mark.asyncio
async def test_client_role_and_user_id_ignored() -> None:
    real = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
    )
    spoof = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=real)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)

    # buyer cannot register seller key even if body says role=seller
    d = await svc.authorize(
        user_id=real.id,
        session_id=None,
        action=Action.seller_key_register,
        request_id="x",
        client_user_id=spoof,
        client_role="both",
    )
    assert d.code == "FORBIDDEN_ROLE"
    # ensure we loaded real user_id not spoof
    repo.get_user.assert_awaited_with(real.id)
