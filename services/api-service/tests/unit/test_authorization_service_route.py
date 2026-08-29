"""Route exclude action role gate."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.authorization.matrix import Action
from app.domain.authorization.route_exclude import RouteCandidate
from app.domain.authorization.service import AuthorizationService
from app.domain.users.models import UserRole, UserStatus


@pytest.mark.asyncio
async def test_seller_cannot_route_exclude() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.seller,
        status=UserStatus.active,
        is_deleted=False,
    )
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="r",
        candidates=[
            RouteCandidate(uuid.uuid4(), uuid.uuid4(), "active"),
        ],
    )
    assert d.code == "FORBIDDEN_ROLE"


@pytest.mark.asyncio
async def test_buyer_filters_self() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
    )
    other = uuid.uuid4()
    self_id = uuid.uuid4()
    other_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()

    async def _own(_rtype: str, rid: uuid.UUID):
        if rid == self_id:
            return SimpleNamespace(
                resource_id=self_id, owner_user_id=user.id, lifecycle_status="active"
            )
        return SimpleNamespace(
            resource_id=other_id, owner_user_id=other, lifecycle_status="active"
        )

    repo.get_ownership = AsyncMock(side_effect=_own)
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="r",
        candidates=[
            RouteCandidate(self_id, user.id, "active"),
            RouteCandidate(other_id, other, "active"),
        ],
    )
    assert d.allowed is True
    assert len(d.filtered_candidates) == 1
    assert d.filtered_candidates[0].owner_user_id == other


@pytest.mark.asyncio
async def test_only_self_no_candidate() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.both,
        status=UserStatus.active,
        is_deleted=False,
    )
    rid = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_id=rid, owner_user_id=user.id, lifecycle_status="active"
        )
    )
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="r",
        candidates=[RouteCandidate(rid, user.id, "active")],
    )
    assert d.code == "NO_ROUTE_CANDIDATE"
    assert d.http_status == 404


@pytest.mark.asyncio
async def test_forged_owner_resolved_from_storage() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
    )
    rid = uuid.uuid4()
    other = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_id=rid, owner_user_id=user.id, lifecycle_status="active"
        )
    )
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="r",
        candidates=[RouteCandidate(rid, other, "active")],
    )
    assert d.code == "NO_ROUTE_CANDIDATE"


@pytest.mark.asyncio
async def test_relabel_disabled_loses_to_server_state() -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
    )
    rid = uuid.uuid4()
    other = uuid.uuid4()
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_id=rid, owner_user_id=other, lifecycle_status="disabled"
        )
    )
    svc = AuthorizationService(repo)
    d = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="r",
        candidates=[RouteCandidate(rid, other, "active")],
    )
    assert d.code == "NO_ROUTE_CANDIDATE"
