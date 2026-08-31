"""Unit tests for session bootstrap / logout authentication (T073)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import AuthSettings
from app.domain.authentication.session_service import SessionService
from app.domain.users.models import UserRole, UserStatus
from app.security.csrf import issue_csrf_token
from app.security.session import generate_session_token, token_digest


def _settings(*, session_version: int = 1, previous: str | None = None) -> AuthSettings:
    key = "tm_test_" + "s" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        session_hmac_key_previous=previous or "",
        session_hmac_key_version=session_version,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        csrf_hmac_key_version=1,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


def _user(
    *,
    status: UserStatus = UserStatus.active,
    is_deleted: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        phone_normalized="13800138000",
        nickname="单元用户",
        role=UserRole.buyer,
        status=status,
        is_deleted=is_deleted,
    )


def _auth_session(
    *,
    user_id: uuid.UUID,
    token_digest_bytes: bytes,
    key_version: int = 1,
    revoked_at: datetime | None = None,
    expires_delta: timedelta = timedelta(minutes=30),
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        token_digest=token_digest_bytes,
        token_key_version=key_version,
        role_snapshot=UserRole.buyer,
        issued_at=now - timedelta(minutes=5),
        expires_at=now + expires_delta,
        revoked_at=revoked_at,
        revocation_reason="logout" if revoked_at else None,
        created_request_id="r",
        delete_after=now + timedelta(days=90),
    )


@pytest.mark.asyncio
async def test_bootstrap_missing_cookie() -> None:
    session = AsyncMock()
    service = SessionService(session, _settings())
    result = await service.bootstrap_session(cookie_value=None, request_id="r1")
    assert result.kind == "unauthenticated"
    assert result.code == "UNAUTHENTICATED"
    assert result.clear_cookie is False


@pytest.mark.asyncio
async def test_bootstrap_unknown_key_version_fail_closed() -> None:
    session = AsyncMock()
    service = SessionService(session, _settings(session_version=1))
    # Cookie claims version 9 which is neither current nor previous.
    result = await service.bootstrap_session(
        cookie_value="9." + "a" * 40,
        request_id="r1",
    )
    assert result.kind == "service_unavailable"
    assert result.http_status == 503
    assert result.code == "SERVICE_UNAVAILABLE"
    assert result.clear_cookie is False


@pytest.mark.asyncio
async def test_bootstrap_expired_and_revoked() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    user = _user()

    expired = _auth_session(
        user_id=user.id,
        token_digest_bytes=digest,
        expires_delta=timedelta(minutes=-1),
    )
    session = AsyncMock()
    service = SessionService(session, settings)
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        return_value=(expired, user)
    )
    result = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-exp"
    )
    assert result.kind == "unauthenticated"
    assert result.clear_cookie is True
    assert result.reject_reason == "expired"

    revoked = _auth_session(
        user_id=user.id,
        token_digest_bytes=digest,
        revoked_at=datetime.now(timezone.utc),
    )
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        return_value=(revoked, user)
    )
    result2 = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-rev"
    )
    assert result2.reject_reason == "revoked"
    assert result2.clear_cookie is True


@pytest.mark.asyncio
async def test_bootstrap_account_disabled() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    user = _user(status=UserStatus.suspended)
    row = _auth_session(user_id=user.id, token_digest_bytes=digest)

    service = SessionService(AsyncMock(), settings)
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        return_value=(row, user)
    )
    service._repo.is_auth_eligible = MagicMock(return_value=False)
    result = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-dis"
    )
    assert result.kind == "unauthenticated"
    assert result.reject_reason == "account_disabled"


@pytest.mark.asyncio
async def test_bootstrap_success_returns_csrf_bound_to_session() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    user = _user()
    row = _auth_session(user_id=user.id, token_digest_bytes=digest)

    service = SessionService(AsyncMock(), settings)
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        return_value=(row, user)
    )
    service._repo.is_auth_eligible = MagicMock(return_value=True)
    result = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-ok"
    )
    assert result.kind == "success"
    assert result.data["user_id"] == str(user.id)
    assert result.data["phone_masked"]
    assert "*" in result.data["phone_masked"]
    expected = issue_csrf_token(csrf_mat.current, csrf_mat.version, row.id)
    assert result.data["csrf_token"] == expected


@pytest.mark.asyncio
async def test_logout_csrf_missing_wrong_and_cross_session() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    row = _auth_session(user_id=uuid.uuid4(), token_digest_bytes=digest)

    service = SessionService(AsyncMock(), settings)
    service._repo.lock_session_by_token_digest = AsyncMock(return_value=row)
    service._repo.rollback = AsyncMock()
    service._repo.revoke_session = AsyncMock(return_value=True)
    service._repo.append_security_event = AsyncMock()
    service._repo.commit = AsyncMock()

    missing = await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=None,
        request_id="r-csrf-miss",
    )
    assert missing.kind == "csrf_invalid"
    assert missing.clear_cookie is False
    service._repo.revoke_session.assert_not_called()

    wrong = await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=f"{csrf_mat.version}." + "x" * 40,
        request_id="r-csrf-wrong",
    )
    assert wrong.kind == "csrf_invalid"

    other_sid = uuid.uuid4()
    cross = issue_csrf_token(csrf_mat.current, csrf_mat.version, other_sid)
    cross_res = await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=cross,
        request_id="r-csrf-cross",
    )
    assert cross_res.kind == "csrf_invalid"
    service._repo.revoke_session.assert_not_called()

    good = issue_csrf_token(csrf_mat.current, csrf_mat.version, row.id)
    ok = await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=good,
        request_id="r-csrf-ok",
    )
    assert ok.kind == "success"
    assert ok.clear_cookie is True
    service._repo.revoke_session.assert_called_once()


@pytest.mark.asyncio
async def test_logout_old_cookie_only_revokes_exact_session() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    row = _auth_session(user_id=uuid.uuid4(), token_digest_bytes=digest)

    service = SessionService(AsyncMock(), settings)
    service._repo.lock_session_by_token_digest = AsyncMock(return_value=row)
    service._repo.revoke_session = AsyncMock(return_value=True)
    service._repo.append_security_event = AsyncMock()
    service._repo.commit = AsyncMock()
    service._repo.rollback = AsyncMock()

    csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, row.id)
    await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=csrf,
        request_id="r-exact",
    )
    # Must lock by token digest, not by user_id bulk revoke.
    service._repo.lock_session_by_token_digest.assert_awaited_once()
    kwargs = service._repo.lock_session_by_token_digest.await_args.kwargs
    assert kwargs["token_digest"] == digest
    assert kwargs["token_key_version"] == mat.version
    service._repo.revoke_session.assert_awaited_once()
    # revoke_session receives the exact locked row
    assert service._repo.revoke_session.await_args.args[0] is row


@pytest.mark.asyncio
async def test_logout_already_revoked_is_idempotent() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    row = _auth_session(
        user_id=uuid.uuid4(),
        token_digest_bytes=digest,
        revoked_at=datetime.now(timezone.utc),
    )
    service = SessionService(AsyncMock(), settings)
    service._repo.lock_session_by_token_digest = AsyncMock(return_value=row)
    service._repo.rollback = AsyncMock()
    service._repo.revoke_session = AsyncMock()

    result = await service.logout_session(
        cookie_value=token.cookie_value,
        csrf_presented=None,  # not required when already invalid
        request_id="r-idemp",
    )
    assert result.kind == "success"
    assert result.clear_cookie is True
    service._repo.revoke_session.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_db_error_is_service_unavailable() -> None:
    from sqlalchemy.exc import OperationalError

    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)

    service = SessionService(AsyncMock(), settings)
    service._repo.get_session_with_user_by_token_digest = AsyncMock(
        side_effect=OperationalError("stmt", {}, Exception("down"))
    )
    result = await service.bootstrap_session(
        cookie_value=token.cookie_value, request_id="r-db"
    )
    assert result.kind == "service_unavailable"
    assert result.http_status == 503


def _revoke_all_service(
    settings: AuthSettings,
    *,
    row: SimpleNamespace | None,
    user: SimpleNamespace | None = None,
) -> SessionService:
    service = SessionService(AsyncMock(), settings)
    service._repo.lock_session_by_token_digest = AsyncMock(return_value=row)
    service._repo.lock_user_by_id = AsyncMock(return_value=user)
    service._repo.rollback = AsyncMock()
    service._repo.commit = AsyncMock()
    service._repo.bump_session_generation = AsyncMock()
    service._repo.revoke_unrevoked_sessions = AsyncMock()
    service._repo.append_security_event = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_revoke_all_missing_cookie() -> None:
    service = SessionService(AsyncMock(), _settings())
    result = await service.revoke_all_sessions(
        cookie_value=None, csrf_presented=None, request_id="r-none"
    )
    assert result.kind == "unauthenticated"
    assert result.clear_cookie is True


@pytest.mark.asyncio
async def test_revoke_all_unknown_session_key_version() -> None:
    settings = _settings(session_version=2, previous="")
    token = generate_session_token(1)
    service = SessionService(AsyncMock(), settings)
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented="1.aaa",
        request_id="r-ver",
    )
    assert result.kind == "service_unavailable"
    assert result.http_status == 503


@pytest.mark.asyncio
async def test_revoke_all_already_revoked_session() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    row = _auth_session(
        user_id=uuid.uuid4(),
        token_digest_bytes=digest,
        revoked_at=datetime.now(timezone.utc),
    )
    service = _revoke_all_service(settings, row=row)
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented="1.x",
        request_id="r-revoked",
    )
    assert result.kind == "unauthenticated"
    service._repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_all_csrf_invalid() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    user = _user()
    row = _auth_session(user_id=user.id, token_digest_bytes=digest)
    service = _revoke_all_service(settings, row=row, user=user)
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented="1.not-a-valid-csrf",
        request_id="r-csrf",
    )
    assert result.kind == "csrf_invalid"
    assert result.http_status == 403
    service._repo.bump_session_generation.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_all_user_missing() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    row = _auth_session(user_id=uuid.uuid4(), token_digest_bytes=digest)
    csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, row.id)
    service = _revoke_all_service(settings, row=row, user=None)
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented=csrf,
        request_id="r-nouser",
    )
    assert result.kind == "unauthenticated"
    service._repo.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_all_success_bumps_generation() -> None:
    settings = _settings()
    mat = settings.key_material("session")
    csrf_mat = settings.key_material("csrf")
    token = generate_session_token(mat.version)
    digest = token_digest(mat.current, token.opaque_secret)
    user = _user()
    row = _auth_session(user_id=user.id, token_digest_bytes=digest)
    csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, row.id)
    service = _revoke_all_service(settings, row=row, user=user)
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented=csrf,
        request_id="r-all",
    )
    assert result.kind == "success"
    assert result.data == {"logged_out": True, "scope": "all"}
    assert result.clear_cookie is True
    service._repo.bump_session_generation.assert_awaited()
    service._repo.revoke_unrevoked_sessions.assert_awaited()
    service._repo.commit.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_all_db_error_is_service_unavailable() -> None:
    from sqlalchemy.exc import OperationalError

    settings = _settings()
    mat = settings.key_material("session")
    token = generate_session_token(mat.version)
    service = SessionService(AsyncMock(), settings)
    service._repo.lock_session_by_token_digest = AsyncMock(
        side_effect=OperationalError("stmt", {}, Exception("down"))
    )
    result = await service.revoke_all_sessions(
        cookie_value=token.cookie_value,
        csrf_presented="1.x",
        request_id="r-db-all",
    )
    assert result.kind == "service_unavailable"
    assert result.http_status == 503
