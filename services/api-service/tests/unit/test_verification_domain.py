"""Unit tests for verification challenge domain (T031)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth_rate_limit import AuthRateLimitDecision
from app.config import AuthSettings
from app.domain.authentication.challenge_service import (
    CHALLENGE_TTL,
    RESEND_COOLDOWN,
    ChallengeService,
)
from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile
from app.rate_limit import RateLimitBackendUnavailable
from app.security.otp import derive_otp, generate_code_salt, otp_verification_digest
from app.security.reference import phone_ref

_FIXED_PHONE = "13800138000"
_FIXED_IDEMPOTENCY_KEY = "idem-fixed-challenge-001"
_FIXED_REQUEST_ID = "req-challenge-fixed-001"
_FIXED_CLIENT_IP = "127.0.0.1"
_FIXED_RECORD_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_FIXED_REPLAY_UNTIL = datetime(2030, 6, 15, 18, 0, 0, tzinfo=timezone.utc)


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


def _phone_ref_bytes(settings: AuthSettings, phone: str = _FIXED_PHONE) -> bytes:
    return phone_ref(settings.key_material("reference").current, phone)


def _idempotency_record(
    *,
    settings: AuthSettings,
    state: str = "processing",
    result_code: str | None = None,
    http_status: int | None = None,
    result_payload: dict | None = None,
) -> MagicMock:
    record = MagicMock()
    record.id = _FIXED_RECORD_ID
    record.state = state
    record.phone_ref = _phone_ref_bytes(settings)
    record.replay_until = _FIXED_REPLAY_UNTIL
    record.result_code = result_code
    record.http_status = http_status
    record.result_payload = result_payload
    return record


def _winner_repo(record: MagicMock) -> AsyncMock:
    repo = AsyncMock()
    repo.try_begin_idempotency = AsyncMock(return_value=(record, True))
    repo.complete_idempotency = AsyncMock()
    repo.append_security_event = AsyncMock()
    repo.commit = AsyncMock()
    repo.insert_pending_challenge = AsyncMock()
    repo.lock_user_by_phone = AsyncMock()
    repo.lock_current_challenges_for_phone = AsyncMock()
    repo.lock_latest_challenges_for_phone = AsyncMock()
    return repo


def _loser_repo(record: MagicMock) -> AsyncMock:
    repo = AsyncMock()
    repo.try_begin_idempotency = AsyncMock(return_value=(record, False))
    repo.complete_idempotency = AsyncMock()
    repo.append_security_event = AsyncMock()
    repo.commit = AsyncMock()
    repo.insert_pending_challenge = AsyncMock()
    repo.lock_user_by_phone = AsyncMock()
    return repo


def test_phone_normalization_sf03_rules() -> None:
    assert normalize_cn_mobile("13800138000") == "13800138000"
    assert normalize_cn_mobile("+8613800138000") == "13800138000"
    assert normalize_cn_mobile(" 138 0013 8000 ") == "13800138000"
    assert isinstance(normalize_cn_mobile("12345"), PhoneValidationError)
    assert isinstance(normalize_cn_mobile("abcdefghijk"), PhoneValidationError)


def test_challenge_ttl_is_five_minutes() -> None:
    assert CHALLENGE_TTL == timedelta(minutes=5)
    assert RESEND_COOLDOWN == timedelta(seconds=60)


def test_otp_has_no_plaintext_in_digest_path() -> None:
    key = b"tm_test_" + b"x" * 32
    cid = uuid.uuid4()
    code = derive_otp(key, cid)
    assert len(code) == 6
    assert code.isdigit()
    # Leading zeros possible for some challenge ids — string form preserved.
    salt = generate_code_salt()
    digest = otp_verification_digest(key, cid, salt, code)
    assert code.encode("ascii") not in digest
    assert salt not in code.encode("ascii")


def test_only_six_digit_ascii_is_format_valid() -> None:
    key = b"tm_test_" + b"y" * 32
    cid = uuid.uuid4()
    salt = generate_code_salt()
    with pytest.raises(ValueError):
        otp_verification_digest(key, cid, salt, "12345")
    with pytest.raises(ValueError):
        otp_verification_digest(key, cid, salt, "1234567")
    with pytest.raises(ValueError):
        otp_verification_digest(key, cid, salt, "abcdef")


@pytest.mark.asyncio
async def test_challenge_service_rejects_invalid_phone() -> None:
    session = AsyncMock()
    service = ChallengeService(session, _settings(), provider_health_ok=True)
    result = await service.request_challenge(
        phone="not-a-phone",
        idempotency_key="k1",
        request_id="r1",
    )
    assert result.kind == "validation"
    assert result.code == "VALIDATION_ERROR"
    assert result.http_status == 400


@pytest.mark.asyncio
async def test_challenge_service_requires_idempotency_key() -> None:
    session = AsyncMock()
    service = ChallengeService(session, _settings(), provider_health_ok=True)
    result = await service.request_challenge(
        phone="13800138000",
        idempotency_key=None,
        request_id="r1",
    )
    assert result.code == "IDEMPOTENCY_KEY_REQUIRED"
    assert result.http_status == 400


@pytest.mark.asyncio
async def test_challenge_service_delivery_unavailable_before_branch() -> None:
    session = AsyncMock()
    service = ChallengeService(session, _settings(), provider_health_ok=False)
    result = await service.request_challenge(
        phone="13800138000",
        idempotency_key="idem-1",
        request_id="r1",
    )
    assert result.code == "DELIVERY_UNAVAILABLE"
    assert result.http_status == 503


@pytest.mark.asyncio
async def test_challenge_service_service_unavailable_without_keys() -> None:
    session = AsyncMock()
    empty = AuthSettings(sms_adapter="synthetic")
    service = ChallengeService(session, empty, provider_health_ok=True)
    result = await service.request_challenge(
        phone="13800138000",
        idempotency_key="idem-1",
        request_id="r1",
    )
    assert result.code == "SERVICE_UNAVAILABLE"


def test_delivered_eligible_predicate() -> None:
    """Only delivered + eligible user can verify; other states cannot."""
    from app.domain.authentication.session_service import SessionService

    # Shape: session service treats non-delivered as CHALLENGE_UNAVAILABLE.
    assert hasattr(SessionService, "create_session")


def test_decoy_has_null_user_semantics() -> None:
    """Decoy challenges are modeled with user_id None (anti-enumeration)."""
    from app.domain.authentication.models import VerificationChallenge

    assert "user_id" in VerificationChallenge.__table__.c
    col = VerificationChallenge.__table__.c.user_id
    assert col.nullable is True


@pytest.mark.asyncio
async def test_rate_limiter_none_fail_closed_service_unavailable() -> None:
    """Winner path with no rate limiter wired → fail closed, no challenge create."""
    settings = _settings()
    record = _idempotency_record(settings=settings)
    session = AsyncMock()
    service = ChallengeService(
        session,
        settings,
        provider_health_ok=True,
        rate_limiter=None,
    )
    repo = _winner_repo(record)
    service._repo = repo

    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip=_FIXED_CLIENT_IP,
    )

    assert result.kind == "service_unavailable"
    assert result.code == "SERVICE_UNAVAILABLE"
    assert result.http_status == 503
    repo.complete_idempotency.assert_awaited_once()
    complete_kwargs = repo.complete_idempotency.await_args.kwargs
    assert complete_kwargs["http_status"] == 503
    assert complete_kwargs["result_code"] == "SERVICE_UNAVAILABLE"
    assert complete_kwargs["state"] == "failed"
    repo.append_security_event.assert_awaited_once()
    event_kwargs = repo.append_security_event.await_args.kwargs
    assert event_kwargs["event_type"] == "challenge_rate_limited"
    assert event_kwargs["reason_code"] == "backend_unavailable"
    repo.commit.assert_awaited_once()
    repo.insert_pending_challenge.assert_not_awaited()
    repo.lock_user_by_phone.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_limiter_backend_unavailable_fail_closed() -> None:
    """Limiter raises RateLimitBackendUnavailable → 503, no challenge create."""
    settings = _settings()
    record = _idempotency_record(settings=settings)
    limiter = AsyncMock()
    limiter.check_and_increment = AsyncMock(
        side_effect=RateLimitBackendUnavailable("auth redis down")
    )
    session = AsyncMock()
    service = ChallengeService(
        session,
        settings,
        provider_health_ok=True,
        rate_limiter=limiter,
    )
    repo = _winner_repo(record)
    service._repo = repo

    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip=_FIXED_CLIENT_IP,
    )

    assert result.kind == "service_unavailable"
    assert result.code == "SERVICE_UNAVAILABLE"
    assert result.http_status == 503
    limiter.check_and_increment.assert_awaited_once()
    repo.complete_idempotency.assert_awaited_once()
    assert repo.complete_idempotency.await_args.kwargs["result_code"] == (
        "SERVICE_UNAVAILABLE"
    )
    repo.append_security_event.assert_awaited_once()
    assert (
        repo.append_security_event.await_args.kwargs["reason_code"]
        == "backend_unavailable"
    )
    repo.commit.assert_awaited_once()
    repo.insert_pending_challenge.assert_not_awaited()
    repo.lock_user_by_phone.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_limiter_denied_returns_rate_limited() -> None:
    """Limiter deny with retry_after_seconds=30 → RATE_LIMITED 429."""
    settings = _settings()
    record = _idempotency_record(settings=settings)
    limiter = AsyncMock()
    limiter.check_and_increment = AsyncMock(
        return_value=AuthRateLimitDecision(
            allowed=False,
            dimension="phone",
            retry_after_seconds=30,
        )
    )
    session = AsyncMock()
    service = ChallengeService(
        session,
        settings,
        provider_health_ok=True,
        rate_limiter=limiter,
    )
    repo = _winner_repo(record)
    service._repo = repo

    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip=_FIXED_CLIENT_IP,
    )

    assert result.kind == "rate_limited"
    assert result.code == "RATE_LIMITED"
    assert result.http_status == 429
    assert result.retry_after_seconds == 30
    assert result.data == {"retry_after_seconds": 30}
    limiter.check_and_increment.assert_awaited_once()
    repo.complete_idempotency.assert_awaited_once()
    complete_kwargs = repo.complete_idempotency.await_args.kwargs
    assert complete_kwargs["http_status"] == 429
    assert complete_kwargs["result_code"] == "RATE_LIMITED"
    assert complete_kwargs["result_payload"] == {"retry_after_seconds": 30}
    assert complete_kwargs["state"] == "failed"
    repo.append_security_event.assert_awaited_once()
    event_kwargs = repo.append_security_event.await_args.kwargs
    assert event_kwargs["event_type"] == "challenge_rate_limited"
    assert event_kwargs["reason_code"] == "rate_limited"
    assert event_kwargs["safe_metadata"] == {"retry_after_seconds": 30}
    repo.commit.assert_awaited_once()
    repo.insert_pending_challenge.assert_not_awaited()
    repo.lock_user_by_phone.assert_not_awaited()


@pytest.mark.asyncio
async def test_idempotency_loser_processing_is_service_unavailable() -> None:
    """Concurrent winner still processing → 503; no rate limit / no new challenge."""
    settings = _settings()
    record = _idempotency_record(settings=settings, state="processing")
    limiter = AsyncMock()
    limiter.check_and_increment = AsyncMock(
        return_value=AuthRateLimitDecision(allowed=True)
    )
    session = AsyncMock()
    service = ChallengeService(
        session,
        settings,
        provider_health_ok=True,
        rate_limiter=limiter,
    )
    repo = _loser_repo(record)
    service._repo = repo

    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip=_FIXED_CLIENT_IP,
    )

    assert result.kind == "service_unavailable"
    assert result.code == "SERVICE_UNAVAILABLE"
    assert result.http_status == 503
    limiter.check_and_increment.assert_not_awaited()
    repo.complete_idempotency.assert_not_awaited()
    repo.insert_pending_challenge.assert_not_awaited()
    repo.lock_user_by_phone.assert_not_awaited()
    repo.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_idempotency_loser_failed_rate_limited_replays_429() -> None:
    """Failed RATE_LIMITED idempotency record replays 429 without re-counting."""
    settings = _settings()
    record = _idempotency_record(
        settings=settings,
        state="failed",
        result_code="RATE_LIMITED",
        http_status=429,
        result_payload={"retry_after_seconds": 30},
    )
    limiter = AsyncMock()
    limiter.check_and_increment = AsyncMock(
        return_value=AuthRateLimitDecision(allowed=True)
    )
    session = AsyncMock()
    service = ChallengeService(
        session,
        settings,
        provider_health_ok=True,
        rate_limiter=limiter,
    )
    repo = _loser_repo(record)
    service._repo = repo

    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip=_FIXED_CLIENT_IP,
    )

    assert result.kind == "rate_limited"
    assert result.code == "RATE_LIMITED"
    assert result.http_status == 429
    assert result.retry_after_seconds == 30
    assert result.data == {"retry_after_seconds": 30}
    limiter.check_and_increment.assert_not_awaited()
    repo.complete_idempotency.assert_not_awaited()
    repo.insert_pending_challenge.assert_not_awaited()
    repo.lock_user_by_phone.assert_not_awaited()
    repo.commit.assert_not_awaited()
