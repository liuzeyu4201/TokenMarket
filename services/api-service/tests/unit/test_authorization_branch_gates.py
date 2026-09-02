"""Branch coverage for authorization evaluate fail-closed and mutation paths."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.domain.authorization.audit import event_type_for
from app.domain.authorization.matrix import Action
from app.domain.authorization.models import _utcnow
from app.domain.authorization.outbox_worker import _maybe_dt, _maybe_uuid
from app.domain.authorization.route_exclude import RouteCandidate
from app.domain.authorization.service import AuthorizationService
from app.domain.authorization.workspace import (
    default_workspace,
    effective_role,
    workspace_allowed,
)
from app.domain.users.models import UserRole, UserStatus


def _user(*, role: UserRole = UserRole.buyer, status: UserStatus = UserStatus.active):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        status=status,
        is_deleted=False,
    )


def _repo(user) -> MagicMock:
    repo = MagicMock()
    repo.get_user = AsyncMock(return_value=user)
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.insert_security_event = AsyncMock()
    repo.get_ownership = AsyncMock(return_value=None)
    repo.create_ownership = AsyncMock()
    repo.update_ownership_status = AsyncMock()
    return repo


def _db_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("down"))


def test_workspace_lens_unknown_and_seller_passthrough() -> None:
    assert workspace_allowed("buyer", "admin") is False
    assert default_workspace("seller") == "seller"
    assert effective_role("seller", None) == "seller"
    assert effective_role("seller", "seller") == "seller"
    assert effective_role("buyer", "seller") == ""


def test_helpers_preserve_uuid_and_datetime() -> None:
    uid = uuid.uuid4()
    assert _maybe_uuid(uid) is uid
    now = _utcnow()
    assert now.tzinfo is not None
    assert _maybe_dt(now) is now


def test_event_type_for_allowed_without_reason() -> None:
    assert event_type_for(None, allowed=True, is_state_change=False) == "authz.allowed"


@pytest.mark.asyncio
async def test_invalid_action_is_validation() -> None:
    svc = AuthorizationService(_repo(_user()))
    decision = await svc.authorize(
        user_id=uuid.uuid4(),
        session_id=None,
        action="not.an.action",
        request_id="r",
    )
    assert decision.allowed is False
    assert decision.code == "VALIDATION_ERROR"
    assert decision.http_status == 400


@pytest.mark.asyncio
async def test_user_load_operational_error_is_unavailable() -> None:
    repo = _repo(_user())
    repo.get_user = AsyncMock(side_effect=_db_error())
    svc = AuthorizationService(repo)
    decision = await svc.authorize(
        user_id=uuid.uuid4(),
        session_id=None,
        action=Action.project_read,
        request_id="r",
    )
    assert decision.allowed is False
    assert decision.http_status == 503


@pytest.mark.asyncio
async def test_create_ownership_mutation_and_db_failure() -> None:
    user = _user()
    rid = uuid.uuid4()
    row = SimpleNamespace(
        resource_type="proxy_key",
        resource_id=rid,
        owner_user_id=user.id,
        lifecycle_status="active",
        version=1,
    )
    repo = _repo(user)
    repo.create_ownership = AsyncMock(return_value=row)
    svc = AuthorizationService(repo)
    ok = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="c1",
        apply_mutation=True,
        resource_id=rid,
    )
    assert ok.allowed is True
    assert ok.resource_id == rid
    repo.create_ownership = AsyncMock(side_effect=_db_error())
    down = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_create,
        request_id="c2",
        apply_mutation=True,
        resource_id=uuid.uuid4(),
    )
    assert down.allowed is False
    assert down.http_status == 503
    repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_ownership_load_error_and_inactive_proxy_use() -> None:
    user = _user()
    rid = uuid.uuid4()
    repo = _repo(user)
    repo.get_ownership = AsyncMock(side_effect=_db_error())
    svc = AuthorizationService(repo)
    down = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_use,
        request_id="u1",
        resource_type="proxy_key",
        resource_id=rid,
    )
    assert down.http_status == 503
    repo.get_ownership = AsyncMock(
        return_value=SimpleNamespace(
            resource_type="proxy_key",
            resource_id=rid,
            owner_user_id=user.id,
            lifecycle_status="disabled",
            version=1,
        )
    )
    inactive = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_use,
        request_id="u2",
        resource_type="proxy_key",
        resource_id=rid,
    )
    assert inactive.allowed is False
    assert inactive.http_status == 404


@pytest.mark.asyncio
async def test_update_mutation_db_failure() -> None:
    user = _user()
    rid = uuid.uuid4()
    row = SimpleNamespace(
        resource_type="proxy_key",
        resource_id=rid,
        owner_user_id=user.id,
        lifecycle_status="active",
        version=1,
    )
    repo = _repo(user)
    repo.get_ownership = AsyncMock(return_value=row)
    repo.update_ownership_status = AsyncMock(side_effect=_db_error())
    svc = AuthorizationService(repo)
    decision = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.proxy_key_revoke,
        request_id="rev",
        resource_type="proxy_key",
        resource_id=rid,
        apply_mutation=True,
    )
    assert decision.http_status == 503


@pytest.mark.asyncio
async def test_route_candidates_load_missing_as_disabled() -> None:
    user = _user()
    missing = uuid.uuid4()
    repo = _repo(user)
    repo.get_ownership = AsyncMock(return_value=None)
    svc = AuthorizationService(repo)
    decision = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.route_candidate_exclude_self,
        request_id="rt",
        candidates=[
            RouteCandidate(
                resource_id=missing,
                owner_user_id=uuid.UUID(int=0),
                lifecycle_status="active",
            )
        ],
    )
    assert decision.allowed is False
    assert decision.code == "NO_ROUTE_CANDIDATE"


@pytest.mark.asyncio
async def test_audit_persist_failure_and_commit_failure() -> None:
    user = _user()
    repo = _repo(user)
    svc = AuthorizationService(repo)
    svc._persist_audit = AsyncMock(return_value=False)  # type: ignore[method-assign]
    denied = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.seller_key_read,
        request_id="a1",
        resource_type="seller_key",
        resource_id=uuid.uuid4(),
    )
    assert denied.http_status == 503
    svc._persist_audit = AsyncMock(return_value=True)  # type: ignore[method-assign]
    repo.commit = AsyncMock(side_effect=_db_error())
    down = await svc.authorize(
        user_id=user.id,
        session_id=None,
        action=Action.project_read,
        request_id="a2",
        resource_type="project",
        resource_id=uuid.uuid4(),
    )
    assert down.http_status == 503
