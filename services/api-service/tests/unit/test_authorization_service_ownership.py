"""Ownership and revoke→disabled unit tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.matrix import Action
from app.domain.authorization.service import AuthorizationService
from app.domain.users.models import UserRole, UserStatus


def _user(role: UserRole = UserRole.seller):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        status=UserStatus.active,
        is_deleted=False,
    )


@pytest.mark.asyncio
async def test_not_owner_and_missing_same_code() -> None:
    user = _user()
    other = uuid.uuid4()
    rid = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_type="seller_key",
            resource_id=rid,
            owner_user_id=other,
            lifecycle_status="active",
            version=1,
        )
    )
    svc = AuthorizationService(repo)
    d1 = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_read,
        request_id="a",
        resource_type="seller_key",
        resource_id=rid,
    )
    repo.get_ownership = AsyncMock(return_value=None)
    d2 = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_read,
        request_id="b",
        resource_type="seller_key",
        resource_id=uuid.uuid4(),
    )
    assert d1.code == d2.code == "RESOURCE_NOT_FOUND"
    assert d1.http_status == d2.http_status == 404


@pytest.mark.asyncio
async def test_soft_deleted_not_found() -> None:
    user = _user()
    rid = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_type="seller_key",
            resource_id=rid,
            owner_user_id=user.id,
            lifecycle_status="soft_deleted",
            version=1,
        )
    )
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_read,
        request_id="c",
        resource_type="seller_key",
        resource_id=rid,
    )
    assert d.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_revoke_sets_disabled() -> None:
    user = _user(UserRole.buyer)
    rid = uuid.uuid4()
    row = SimpleNamespace(
        resource_type="proxy_key",
        resource_id=rid,
        owner_user_id=user.id,
        lifecycle_status="active",
        version=1,
    )

    async def _update(r, *, lifecycle_status: str):
        r.lifecycle_status = lifecycle_status
        r.version += 1
        return r

    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.get_ownership = AsyncMock(return_value=row)
    repo.update_ownership_status = AsyncMock(side_effect=_update)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_revoke,
        request_id="rev",
        resource_type="proxy_key",
        resource_id=rid,
        apply_mutation=True,
    )
    assert d.allowed is True
    assert d.resource is not None
    assert d.resource["lifecycle_status"] == "disabled"
    repo.update_ownership_status.assert_awaited()
