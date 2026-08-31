"""Unit tests for ProfileCompletionService (deterministic 80% auth gate)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import AuthSettings
from app.domain.authentication.profile_service import ProfileCompletionService
from app.domain.users.models import UserRole, UserStatus
from app.security.profile_token import generate_profile_token


def _settings(*, session_version: int = 1) -> AuthSettings:
    key = "tm_test_" + "p" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        session_hmac_key_version=session_version,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        csrf_hmac_key_version=1,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        nickname="补全用户",
        phone_normalized="13800138000",
        role=UserRole.buyer,
        status=UserStatus.active,
    )


def _service(settings: AuthSettings) -> ProfileCompletionService:
    svc = ProfileCompletionService(AsyncMock(), settings)
    svc._repo.rollback = AsyncMock()
    svc._repo.commit = AsyncMock()
    svc._repo.append_security_event = AsyncMock()
    svc._repo.bump_session_generation = AsyncMock(return_value=1)
    return svc


@pytest.mark.asyncio
async def test_complete_missing_cookie() -> None:
    svc = _service(_settings())
    result = await svc.complete(
        cookie_value=None,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r1",
    )
    assert result.kind == "unauthenticated"
    assert result.code == "AUTH_VERIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_complete_unknown_key_version() -> None:
    settings = _settings(session_version=2)
    token = generate_profile_token(1)
    svc = _service(settings)
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r-ver",
    )
    assert result.kind == "service_unavailable"
    assert result.http_status == 503


@pytest.mark.asyncio
async def test_complete_expired_intent() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    svc._repo.get_open_intent_by_digest = AsyncMock(return_value=None)
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r-exp",
    )
    assert result.kind == "unauthenticated"
    assert result.code == "PROFILE_EXPIRED"
    svc._repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_complete_register_conflict() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    svc._repo.get_open_intent_by_digest = AsyncMock(
        return_value=SimpleNamespace(phone_normalized="13800138000")
    )
    svc._users.register = AsyncMock(
        return_value=SimpleNamespace(
            kind="conflict",
            http_status=409,
            code="PHONE_ALREADY_REGISTERED",
            message="taken",
            data=None,
        )
    )
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key="k",
        request_id="r-conf",
    )
    assert result.kind == "conflict"
    assert result.http_status == 409


@pytest.mark.asyncio
async def test_complete_user_missing_after_register() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    svc._repo.get_open_intent_by_digest = AsyncMock(
        return_value=SimpleNamespace(phone_normalized="13800138000")
    )
    uid = uuid.uuid4()
    svc._users.register = AsyncMock(
        return_value=SimpleNamespace(
            kind="success", data={"user_id": str(uid)}, http_status=200
        )
    )
    svc._repo.lock_user_by_id = AsyncMock(return_value=None)
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r-nouser",
    )
    assert result.kind == "service_unavailable"
    svc._repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_complete_insert_integrity_error() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    intent = SimpleNamespace(phone_normalized="13800138000", consumed_at=None)
    svc._repo.get_open_intent_by_digest = AsyncMock(return_value=intent)
    user = _user()
    svc._users.register = AsyncMock(
        return_value=SimpleNamespace(
            kind="success", data={"user_id": str(user.id)}, http_status=200
        )
    )
    svc._repo.lock_user_by_id = AsyncMock(return_value=user)
    svc._repo.insert_session = AsyncMock(
        side_effect=IntegrityError("stmt", {}, Exception("dup"))
    )
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r-ins",
    )
    assert result.kind == "service_unavailable"
    svc._repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_complete_commit_conflict() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    intent = SimpleNamespace(phone_normalized="13800138000", consumed_at=None)
    svc._repo.get_open_intent_by_digest = AsyncMock(return_value=intent)
    user = _user()
    svc._users.register = AsyncMock(
        return_value=SimpleNamespace(
            kind="success", data={"user_id": str(user.id)}, http_status=200
        )
    )
    svc._repo.lock_user_by_id = AsyncMock(return_value=user)
    svc._repo.insert_session = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid.uuid4(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            workspace="buyer",
        )
    )
    svc._repo.commit = AsyncMock(
        side_effect=IntegrityError("stmt", {}, Exception("dup"))
    )
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key=None,
        request_id="r-commit",
    )
    assert result.kind == "conflict"
    assert result.code == "PHONE_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_complete_success_naive_expires() -> None:
    settings = _settings()
    token = generate_profile_token(settings.key_material("session").version)
    svc = _service(settings)
    intent = SimpleNamespace(phone_normalized="13800138000", consumed_at=None)
    svc._repo.get_open_intent_by_digest = AsyncMock(return_value=intent)
    user = _user()
    svc._users.register = AsyncMock(
        return_value=SimpleNamespace(
            kind="success", data={"user_id": str(user.id)}, http_status=200
        )
    )
    svc._repo.lock_user_by_id = AsyncMock(return_value=user)
    naive = datetime.now() + timedelta(hours=1)
    svc._repo.insert_session = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid.uuid4(), expires_at=naive, workspace="buyer"
        )
    )
    result = await svc.complete(
        cookie_value=token.cookie_value,
        nickname="N",
        role="buyer",
        idempotency_key="idem",
        request_id="r-ok",
        client_ip="127.0.0.1",
    )
    assert result.kind == "success"
    assert result.cookie_value
    assert result.data["workspace"] == "buyer"
    assert result.data["expires_at"].tzinfo is not None
    svc._repo.commit.assert_awaited()
