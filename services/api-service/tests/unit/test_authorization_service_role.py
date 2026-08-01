"""AuthorizationService role matrix unit tests with mocked repository."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.matrix import Action
from app.domain.authorization.service import AuthorizationService
from app.domain.users.models import UserRole, UserStatus


def _user(role: UserRole, *, status: UserStatus = UserStatus.active, deleted: bool = False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        status=status,
        is_deleted=deleted,
    )


@pytest.mark.asyncio
async def test_buyer_allowed_proxy_denied_seller() -> None:
    user = _user(UserRole.buyer)
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)

    ok = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="r1",
    )
    assert ok.allowed is True

    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_register,
        request_id="r2",
    )
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN_ROLE"
    assert denied.http_status == 403


@pytest.mark.asyncio
async def test_seller_symmetric() -> None:
    user = _user(UserRole.seller)
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)

    rid = uuid.uuid4()
    row = SimpleNamespace(
        resource_type="seller_key",
        resource_id=rid,
        owner_user_id=user.id,
        lifecycle_status="active",
        version=1,
    )
    repo.get_ownership = AsyncMock(return_value=row)

    ok = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_read,
        request_id="r1",
        resource_type="seller_key",
        resource_id=rid,
    )
    assert ok.allowed is True

    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_use,
        request_id="r2",
        resource_type="proxy_key",
        resource_id=uuid.uuid4(),
    )
    assert denied.code == "FORBIDDEN_ROLE"


@pytest.mark.asyncio
async def test_suspended_denied() -> None:
    user = _user(UserRole.both, status=UserStatus.suspended)
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="r1",
    )
    assert d.allowed is False
    assert d.code == "ACCOUNT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_deleted_denied() -> None:
    user = _user(UserRole.buyer, deleted=True)
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="r1",
    )
    assert d.code == "ACCOUNT_UNAVAILABLE"
