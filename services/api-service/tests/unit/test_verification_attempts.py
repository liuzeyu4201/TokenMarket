"""Unit tests: verification attempt lifecycle (T054 / US2).

Covers non-6-digit format (no attempt increment), wrong codes 1–5, terminal
states expired/locked/consumed/superseded, decoy uniform actions, and
successful session issuance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import AuthSettings
from app.domain.authentication.session_service import SessionService
from app.repositories.authentication import MAX_ATTEMPTS
from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.otp import derive_otp, generate_code_salt, otp_verification_digest
from app.security.session import SessionToken

# Fixed fixtures for success-path coverage (no random collision reliance).
_FIXED_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_FIXED_CHALLENGE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_FIXED_SESSION_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
_FIXED_PHONE = "13800138000"
_FIXED_NICKNAME = "登录用户"
_FIXED_SALT = bytes(range(16))
_FIXED_EXPIRES = datetime(2030, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_FIXED_SESSION_EXPIRES = datetime(2030, 6, 15, 13, 0, 0, tzinfo=timezone.utc)
_FIXED_TOKEN = SessionToken(
    key_version=1,
    opaque_secret="A" * 43,
    cookie_value="1." + "A" * 43,
    raw_secret_bytes=b"\x02" * 32,
)


def _settings() -> AuthSettings:
    key = "tm_test_" + "a" * 40
    return AuthSettings(
        session_hmac_key_current=key,
        otp_hmac_key_current=key,
        csrf_hmac_key_current=key,
        reference_hmac_key_current=key,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="synthetic",
    )


def _challenge(
    *,
    state: str = "delivered",
    attempt_count: int = 0,
    user_id: uuid.UUID | None = None,
    expires_delta: timedelta = timedelta(minutes=4),
    code: str | None = None,
    settings: AuthSettings | None = None,
    challenge_id: uuid.UUID | None = None,
    salt: bytes | None = None,
    expires_at: datetime | None = None,
) -> MagicMock:
    settings = settings or _settings()
    cid = challenge_id if challenge_id is not None else uuid.uuid4()
    otp_mat = settings.key_material("otp")
    plain = code or derive_otp(otp_mat.current, cid)
    salt_bytes = salt if salt is not None else generate_code_salt()
    digest = otp_verification_digest(otp_mat.current, cid, salt_bytes, plain)
    now = datetime.now(timezone.utc)
    ch = MagicMock()
    ch.id = cid
    ch.user_id = user_id
    ch.phone_normalized = None
    ch.state = state
    ch.attempt_count = attempt_count
    ch.expires_at = expires_at if expires_at is not None else now + expires_delta
    ch.code_digest = digest
    ch.code_salt = salt_bytes
    ch.code_key_version = otp_mat.version
    ch.invalidated_at = None
    ch.consumed_at = None
    ch.send_started_at = None
    ch._plain = plain
    return ch


def _active_user(
    *,
    user_id: uuid.UUID | None = None,
    phone: str = _FIXED_PHONE,
    nickname: str = _FIXED_NICKNAME,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id if user_id is not None else uuid.uuid4()
    user.status = "active"
    user.is_deleted = False
    user.role = "buyer"
    user.nickname = nickname
    user.phone_normalized = phone
    return user


def _service_with_challenge(
    challenge: MagicMock,
    *,
    user: MagicMock | None = None,
    settings: AuthSettings | None = None,
) -> tuple[SessionService, AsyncMock, AsyncMock]:
    session = AsyncMock()
    settings = settings or _settings()
    service = SessionService(session, settings)

    # Patch repository methods on the service instance.
    repo = AsyncMock()
    service._repo = repo

    async def get_challenge(cid: uuid.UUID) -> MagicMock | None:
        if cid == challenge.id:
            return challenge
        return None

    async def lock_challenge(cid: uuid.UUID) -> MagicMock | None:
        if cid == challenge.id:
            return challenge
        return None

    async def lock_user_by_id(uid: uuid.UUID) -> MagicMock | None:
        return user

    repo.get_challenge = get_challenge
    repo.lock_challenge = lock_challenge
    repo.lock_user_by_id = lock_user_by_id
    repo.is_auth_eligible = (
        lambda u: u is not None
        and getattr(u, "status", None) == "active"
        and not getattr(u, "is_deleted", False)
    )
    repo.append_security_event = AsyncMock()
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.revoke_unrevoked_sessions = AsyncMock(return_value=0)
    repo.bump_session_generation = AsyncMock(return_value=2)
    repo.insert_session = AsyncMock()
    return service, session, repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_code",
    ["12345", "1234567", "abcdef", "12 456", "１２３４５６", "12ab56", ""],
)
async def test_malformed_code_is_validation_without_attempt(bad_code: str) -> None:
    user_id = uuid.uuid4()
    ch = _challenge(user_id=user_id)
    before = ch.attempt_count
    service, _, _ = _service_with_challenge(ch)
    result = await service.create_session(
        challenge_id=ch.id,
        code=bad_code,
        request_id="r-fmt",
    )
    assert result.kind == "validation"
    assert result.code == "VALIDATION_ERROR"
    assert result.http_status == 400
    assert ch.attempt_count == before
    assert ch.state == "delivered"


@pytest.mark.asyncio
async def test_wrong_code_attempts_one_through_four_retry() -> None:
    user_id = uuid.uuid4()
    user = _active_user(user_id=user_id, nickname="u")

    ch = _challenge(user_id=user_id, attempt_count=0)
    service, _, _ = _service_with_challenge(ch, user=user)

    for expected_remaining in (4, 3, 2, 1):
        result = await service.create_session(
            challenge_id=ch.id,
            code="000000",
            request_id=f"r-{expected_remaining}",
        )
        assert result.code == "VERIFICATION_FAILED"
        assert result.http_status == 401
        assert result.data["action"] == "retry_code"
        assert result.data["attempts_remaining"] == expected_remaining
        assert ch.state == "delivered"
        assert ch.code_digest is not None


@pytest.mark.asyncio
async def test_fifth_wrong_code_locks_request_new_code() -> None:
    user_id = uuid.uuid4()
    user = _active_user(user_id=user_id)

    ch = _challenge(user_id=user_id, attempt_count=4)
    service, _, _ = _service_with_challenge(ch, user=user)
    result = await service.create_session(
        challenge_id=ch.id,
        code="000000",
        request_id="r-lock",
    )
    assert result.code == "VERIFICATION_FAILED"
    assert result.data["action"] == "request_new_code"
    assert "attempts_remaining" not in result.data or result.data.get(
        "attempts_remaining"
    ) in (None, 0)
    assert ch.state == "locked"
    assert ch.attempt_count == MAX_ATTEMPTS
    assert ch.code_digest is None
    assert ch.code_salt is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,expected_code,expected_status",
    [
        ("locked", "CHALLENGE_UNAVAILABLE", 409),
        ("consumed", "CHALLENGE_UNAVAILABLE", 409),
        ("superseded", "CHALLENGE_UNAVAILABLE", 409),
        ("delivery_failed", "CHALLENGE_UNAVAILABLE", 409),
        ("pending_delivery", "CHALLENGE_UNAVAILABLE", 409),
        ("dispatching", "CHALLENGE_UNAVAILABLE", 409),
    ],
)
async def test_terminal_states_uniform_unavailable(
    state: str, expected_code: str, expected_status: int
) -> None:
    user_id = uuid.uuid4()
    ch = _challenge(user_id=user_id, state=state, attempt_count=0)
    before = ch.attempt_count
    service, _, _ = _service_with_challenge(ch)
    result = await service.create_session(
        challenge_id=ch.id,
        code="012345",
        request_id="r-term",
    )
    assert result.code == expected_code
    assert result.http_status == expected_status
    assert ch.attempt_count == before


@pytest.mark.asyncio
async def test_expired_maps_challenge_expired() -> None:
    user_id = uuid.uuid4()
    ch = _challenge(
        user_id=user_id,
        state="delivered",
        expires_delta=timedelta(seconds=-1),
    )
    service, _, _ = _service_with_challenge(ch)
    result = await service.create_session(
        challenge_id=ch.id,
        code=ch._plain,
        request_id="r-exp",
    )
    assert result.code == "CHALLENGE_EXPIRED"
    assert result.http_status == 410
    assert ch.state == "expired"


@pytest.mark.asyncio
async def test_decoy_correct_code_uses_attempt_lifecycle() -> None:
    """Decoy never issues a session; correct OTP still counts as a failed attempt."""
    ch = _challenge(user_id=None, attempt_count=0)
    service, _, _ = _service_with_challenge(ch, user=None)
    result = await service.create_session(
        challenge_id=ch.id,
        code=ch._plain,
        request_id="r-decoy",
    )
    assert result.code == "VERIFICATION_FAILED"
    assert result.http_status == 401
    assert result.data["action"] == "retry_code"
    assert result.data["attempts_remaining"] == 4
    assert ch.attempt_count == 1
    assert ch.state == "delivered"
    assert result.cookie_value is None


@pytest.mark.asyncio
async def test_decoy_fifth_failure_locks() -> None:
    ch = _challenge(user_id=None, attempt_count=4)
    service, _, _ = _service_with_challenge(ch, user=None)
    result = await service.create_session(
        challenge_id=ch.id,
        code=ch._plain,
        request_id="r-decoy-lock",
    )
    assert result.code == "VERIFICATION_FAILED"
    assert result.data["action"] == "request_new_code"
    assert ch.state == "locked"


def _issued_auth_session() -> MagicMock:
    auth_session = MagicMock()
    auth_session.id = _FIXED_SESSION_ID
    auth_session.expires_at = _FIXED_SESSION_EXPIRES
    return auth_session


@pytest.mark.asyncio
async def test_correct_otp_issues_session_without_prior_sessions() -> None:
    """Active user + delivered challenge + correct OTP → success, no replace."""
    settings = _settings()
    user = _active_user(user_id=_FIXED_USER_ID)
    ch = _challenge(
        user_id=_FIXED_USER_ID,
        challenge_id=_FIXED_CHALLENGE_ID,
        salt=_FIXED_SALT,
        expires_at=_FIXED_EXPIRES,
        settings=settings,
    )
    service, _, repo = _service_with_challenge(ch, user=user, settings=settings)
    repo.revoke_unrevoked_sessions = AsyncMock(return_value=0)
    repo.insert_session = AsyncMock(return_value=_issued_auth_session())

    with (
        patch(
            "app.domain.authentication.session_service.uuid.uuid4",
            return_value=_FIXED_SESSION_ID,
        ),
        patch(
            "app.domain.authentication.session_service.generate_session_token",
            return_value=_FIXED_TOKEN,
        ),
    ):
        result = await service.create_session(
            challenge_id=_FIXED_CHALLENGE_ID,
            code=ch._plain,
            request_id="r-issue-ok",
        )

    assert result.kind == "success"
    assert result.http_status == 200
    assert result.code == "0"
    assert result.cookie_value == _FIXED_TOKEN.cookie_value
    assert result.cookie_value is not None and result.cookie_value != ""
    assert result.data is not None
    assert result.data["user_id"] == str(_FIXED_USER_ID)
    assert result.data["nickname"] == _FIXED_NICKNAME
    assert result.data["phone_masked"] == "*******8000"
    assert result.data["role"] == "buyer"
    assert "csrf_token" in result.data
    csrf_mat = settings.key_material("csrf")
    assert verify_csrf_token(
        csrf_mat.current,
        csrf_mat.version,
        _FIXED_SESSION_ID,
        result.data["csrf_token"],
    )
    assert result.data["csrf_token"] == issue_csrf_token(
        csrf_mat.current, csrf_mat.version, _FIXED_SESSION_ID
    )

    assert ch.state == "consumed"
    assert ch.code_digest is None
    assert ch.code_salt is None
    assert ch.send_started_at is None
    assert ch.consumed_at is not None

    repo.revoke_unrevoked_sessions.assert_awaited_once()
    repo.insert_session.assert_awaited_once()
    repo.commit.assert_awaited_once()
    repo.rollback.assert_not_awaited()

    event_types = [
        c.kwargs["event_type"] for c in repo.append_security_event.await_args_list
    ]
    assert "session_issued" in event_types
    assert "session_replaced" not in event_types


@pytest.mark.asyncio
async def test_correct_otp_replaces_existing_sessions() -> None:
    """When prior sessions are revoked, emit session_replaced audit event."""
    settings = _settings()
    user = _active_user(user_id=_FIXED_USER_ID)
    ch = _challenge(
        user_id=_FIXED_USER_ID,
        challenge_id=_FIXED_CHALLENGE_ID,
        salt=_FIXED_SALT,
        expires_at=_FIXED_EXPIRES,
        settings=settings,
    )
    service, _, repo = _service_with_challenge(ch, user=user, settings=settings)
    repo.revoke_unrevoked_sessions = AsyncMock(return_value=2)
    repo.insert_session = AsyncMock(return_value=_issued_auth_session())

    with (
        patch(
            "app.domain.authentication.session_service.uuid.uuid4",
            return_value=_FIXED_SESSION_ID,
        ),
        patch(
            "app.domain.authentication.session_service.generate_session_token",
            return_value=_FIXED_TOKEN,
        ),
    ):
        result = await service.create_session(
            challenge_id=_FIXED_CHALLENGE_ID,
            code=ch._plain,
            request_id="r-issue-replace",
        )

    assert result.kind == "success"
    assert result.cookie_value == _FIXED_TOKEN.cookie_value
    assert result.data["user_id"] == str(_FIXED_USER_ID)
    assert result.data["csrf_token"]
    assert ch.state == "consumed"
    assert ch.code_digest is None
    assert ch.code_salt is None
    repo.commit.assert_awaited_once()

    event_types = [
        c.kwargs["event_type"] for c in repo.append_security_event.await_args_list
    ]
    assert "session_issued" in event_types
    assert "session_replaced" in event_types
    issued = next(
        c
        for c in repo.append_security_event.await_args_list
        if c.kwargs["event_type"] == "session_issued"
    )
    assert issued.kwargs["safe_metadata"] == {"replaced": True}
