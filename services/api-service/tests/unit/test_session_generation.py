"""Unit tests: account session generation (SF07)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import AuthSettings
from app.domain.authentication.session_service import SessionService
from app.domain.users.models import UserRole, UserStatus
from app.security.session import generate_session_token, token_digest


def _settings() -> AuthSettings:
    key = "tm_test_" + "g" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


@pytest.mark.asyncio
async def test_bootstrap_rejects_generation_mismatch() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(
        id=uuid.uuid4(),
        phone_normalized="13800138000",
        nickname="世代",
        role=UserRole.buyer,
        status=UserStatus.active,
        is_deleted=False,
        session_generation=3,
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        token_digest=digest,
        token_key_version=mat.version,
        session_generation=2,
        role_snapshot=UserRole.buyer,
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=30),
        revoked_at=None,
        revocation_reason=None,
        created_request_id="r",
        delete_after=now + timedelta(days=90),
    )
    service = SessionService(AsyncMock(), settings)
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        return_value=(row, user)
    )
    service._repo.is_auth_eligible = MagicMock(return_value=True)
    result = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-gen"
    )
    assert result.kind == "unauthenticated"
    assert result.reject_reason == "generation_mismatch"
    assert result.clear_cookie is True
