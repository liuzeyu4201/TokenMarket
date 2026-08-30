"""Workspace lens authorization (SF09)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.matrix import Action
from app.domain.authorization.service import AuthorizationService
from app.domain.authorization.workspace import (
    default_workspace,
    effective_role,
    workspace_allowed,
)
from app.domain.users.models import UserRole, UserStatus


def test_default_and_allowance() -> None:
    assert default_workspace("buyer") == "buyer"
    assert default_workspace("both") == "buyer"
    assert default_workspace("seller") == "seller"
    assert workspace_allowed("both", "seller")
    assert not workspace_allowed("buyer", "seller")
    assert effective_role("both", "seller") == "seller"
    assert effective_role("both", None) == "both"
    assert effective_role("buyer", "seller") == ""


def _user(role: UserRole = UserRole.both) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        status=UserStatus.active,
        is_deleted=False,
    )


def _svc(user: SimpleNamespace) -> AuthorizationService:
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.insert_security_event = AsyncMock()
    return AuthorizationService(repo)


@pytest.mark.asyncio
async def test_both_buyer_workspace_denies_seller_action() -> None:
    user = _user()
    svc = _svc(user)
    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_register,
        request_id="r1",
        workspace="buyer",
        client_workspace="seller",
    )
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN_ROLE"
    assert denied.http_status == 403


@pytest.mark.asyncio
async def test_both_seller_workspace_denies_proxy_create() -> None:
    user = _user()
    svc = _svc(user)
    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="r2",
        workspace="seller",
    )
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN_ROLE"


@pytest.mark.asyncio
async def test_both_without_workspace_keeps_account_matrix() -> None:
    user = _user()
    svc = _svc(user)
    ok = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_register,
        request_id="r3",
        workspace=None,
    )
    assert ok.allowed is True


@pytest.mark.asyncio
async def test_buyer_cannot_use_seller_workspace_lens() -> None:
    user = _user(UserRole.buyer)
    svc = _svc(user)
    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="r4",
        workspace="seller",
    )
    assert denied.allowed is False
    assert denied.code == "FORBIDDEN_ROLE"
