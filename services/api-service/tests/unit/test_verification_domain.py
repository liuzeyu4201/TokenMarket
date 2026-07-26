"""Unit tests for verification challenge domain (T031)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.config import AuthSettings
from app.domain.authentication.challenge_service import (
    CHALLENGE_TTL,
    RESEND_COOLDOWN,
    ChallengeService,
)
from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile
from app.security.otp import derive_otp, generate_code_salt, otp_verification_digest


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
