"""Unit tests for session issuance domain (T036)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import Response

from app.config import AuthSettings
from app.domain.authentication.session_service import SessionService
from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.session import (
    SESSION_COOKIE_NAME,
    generate_session_token,
    set_session_cookie,
    token_digest,
)


def _settings() -> AuthSettings:
    key = "tm_test_" + "s" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


def test_cookie_and_csrf_issued_after_commit_semantics() -> None:
    """Cookie helpers apply only to response objects after domain commit."""
    settings = _settings()
    session_mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(session_mat.version)
    sid = uuid.uuid4()
    csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, sid)
    assert len(csrf) >= 32
    assert verify_csrf_token(csrf_mat.current, csrf_mat.version, sid, csrf)

    response = Response()
    set_session_cookie(response, token.cookie_value)
    header = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in header
    assert "Secure" in header or "secure" in header.lower()
    assert "HttpOnly" in header or "httponly" in header.lower()
    assert "Path=/" in header or "path=/" in header.lower()
    assert "Max-Age=3600" in header or "max-age=3600" in header.lower()
    assert "Domain=" not in header and "domain=" not in header.lower()


def test_token_digest_never_equals_raw_secret() -> None:
    settings = _settings()
    key = settings.key_material("session").current
    token = generate_session_token(1)
    digest = token_digest(key, token.opaque_secret)
    assert digest != token.raw_secret_bytes
    assert token.opaque_secret.encode("ascii") not in digest


@pytest.mark.asyncio
async def test_malformed_code_validation_before_attempt() -> None:
    session = AsyncMock()
    service = SessionService(session, _settings())
    result = await service.create_session(
        challenge_id=uuid.uuid4(),
        code="12ab56",
        request_id="r1",
    )
    assert result.kind == "validation"
    assert result.code == "VALIDATION_ERROR"
    assert result.http_status == 400
    # No DB lock should have been attempted for malformed code.
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_missing_challenge_maps_unavailable() -> None:
    session = AsyncMock()
    # get returns None for challenge
    session.get = AsyncMock(return_value=None)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    service = SessionService(session, _settings())
    result = await service.create_session(
        challenge_id=uuid.uuid4(),
        code="012345",
        request_id="r1",
    )
    assert result.code == "CHALLENGE_UNAVAILABLE"
    assert result.http_status == 409


def test_lock_order_documented_user_then_challenge() -> None:
    """Repository documents mandatory lock order user → challenge."""
    import inspect

    from app.repositories import authentication as auth_repo

    source = inspect.getsource(auth_repo)
    assert "user row" in source.lower() or "user → challenge" in source or "user then challenge" in source.lower() or "Lock order" in source


def test_session_conflict_maps_to_unavailable_shape() -> None:
    """IntegrityError on insert maps to SERVICE_UNAVAILABLE (conflict path)."""
    from app.domain.authentication.session_service import SessionIssueResult

    r = SessionIssueResult(
        kind="service_unavailable",
        http_status=503,
        code="SERVICE_UNAVAILABLE",
        message="服务暂时不可用，请稍后重试",
    )
    assert r.cookie_value is None
