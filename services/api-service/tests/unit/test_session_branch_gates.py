"""Fail-closed session logout / workspace-switch branches."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.config import AuthSettings
from app.domain.authentication.session_service import SessionService
from app.security.session import generate_session_token


def _settings() -> AuthSettings:
    key = "tm_test_" + "k" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


def _db_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("down"))


@pytest.mark.asyncio
async def test_logout_db_error_and_malformed_cookie() -> None:
    settings = _settings()
    svc = SessionService(AsyncMock(), settings)
    svc._repo = AsyncMock()
    svc._repo.lock_session_by_token_digest = AsyncMock(side_effect=_db_error())
    token = generate_session_token(1)
    down = await svc.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=None,
        request_id="r",
    )
    assert down.kind == "service_unavailable"
    missing = await svc.logout_session(
        cookie_value="not-a-cookie",
        csrf_presented=None,
        request_id="r",
    )
    assert missing.kind == "success"
    assert missing.clear_cookie is True


@pytest.mark.asyncio
async def test_switch_workspace_unauthenticated_and_db_error() -> None:
    settings = _settings()
    svc = SessionService(AsyncMock(), settings)
    svc._repo = AsyncMock()
    missing = await svc.switch_workspace(
        cookie_value=None,
        csrf_presented=None,
        target="buyer",
        request_id="r",
    )
    assert missing.kind == "unauthenticated"
    token = generate_session_token(1)
    svc._repo.lock_session_by_token_digest = AsyncMock(side_effect=_db_error())
    down = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert down.kind == "service_unavailable"
    svc._repo.lock_session_by_token_digest = AsyncMock(return_value=None)
    gone = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert gone.kind == "unauthenticated"


@pytest.mark.asyncio
async def test_security_summary_malformed_cookie() -> None:
    svc = SessionService(AsyncMock(), _settings())
    svc._repo = AsyncMock()
    out = await svc.security_summary(cookie_value="bad", request_id="r")
    assert out.kind == "unauthenticated"
    assert out.clear_cookie is True


@pytest.mark.asyncio
async def test_switch_workspace_csrf_user_and_role_denials() -> None:
    settings = _settings()
    svc = SessionService(AsyncMock(), settings)
    repo = AsyncMock()
    repo.rollback = AsyncMock()
    repo.commit = AsyncMock()
    repo.append_security_event = AsyncMock()
    svc._repo = repo
    token = generate_session_token(1)
    sess = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        revoked_at=None,
        workspace="buyer",
    )
    repo.lock_session_by_token_digest = AsyncMock(return_value=sess)
    svc._verify_csrf_for_session = MagicMock(  # type: ignore[method-assign]
        return_value=None
    )
    cfg = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert cfg.kind == "service_unavailable"
    svc._verify_csrf_for_session = MagicMock(  # type: ignore[method-assign]
        return_value=False
    )
    csrf = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert csrf.kind == "csrf_invalid"
    svc._verify_csrf_for_session = MagicMock(  # type: ignore[method-assign]
        return_value=True
    )
    repo.lock_user_by_id = AsyncMock(return_value=None)
    missing_user = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert missing_user.kind == "unauthenticated"
    repo.lock_user_by_id = AsyncMock(
        return_value=SimpleNamespace(id=sess.user_id, role="buyer")
    )
    denied = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert denied.kind == "forbidden"
    revoked = SimpleNamespace(
        id=sess.id, user_id=sess.user_id, revoked_at=object(), workspace="buyer"
    )
    repo.lock_session_by_token_digest = AsyncMock(return_value=revoked)
    gone = await svc.switch_workspace(
        cookie_value=token.cookie_value,
        csrf_presented="x",
        target="seller",
        request_id="r",
    )
    assert gone.kind == "unauthenticated"
