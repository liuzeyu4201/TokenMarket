"""Winner/cooldown/delivery branches for ChallengeService and DeliveryService."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth_rate_limit import AuthRateLimitDecision
from app.config import AuthSettings
from app.domain.authentication.challenge_service import ChallengeService
from app.domain.authentication.delivery_service import DeliveryService
from app.security.reference import phone_ref
from app.sms.port import SmsDeliveryResult

_FIXED_PHONE = "13800138000"
_FIXED_IDEMPOTENCY_KEY = "idem-branch-challenge-001"
_FIXED_REQUEST_ID = "req-branch-challenge-001"
_FIXED_RECORD_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


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


def _record(settings: AuthSettings) -> MagicMock:
    record = MagicMock()
    record.id = _FIXED_RECORD_ID
    record.state = "processing"
    record.phone_ref = phone_ref(
        settings.key_material("reference").current, _FIXED_PHONE
    )
    record.replay_until = datetime(2030, 6, 15, tzinfo=timezone.utc)
    record.result_code = None
    record.http_status = None
    record.result_payload = None
    return record


def _winner_service() -> tuple[ChallengeService, AsyncMock, MagicMock]:
    settings = _settings()
    record = _record(settings)
    limiter = AsyncMock()
    limiter.check_and_increment = AsyncMock(
        return_value=AuthRateLimitDecision(allowed=True)
    )
    service = ChallengeService(
        AsyncMock(),
        settings,
        provider_health_ok=True,
        rate_limiter=limiter,
    )
    repo = AsyncMock()
    repo.try_begin_idempotency = AsyncMock(return_value=(record, True))
    repo.complete_idempotency = AsyncMock()
    repo.append_security_event = AsyncMock()
    repo.commit = AsyncMock()
    repo.lock_user_by_phone = AsyncMock(return_value=None)
    repo.is_auth_eligible = MagicMock(return_value=False)
    repo.lock_current_challenges_for_phone = AsyncMock(return_value=[])
    repo.lock_latest_challenges_for_phone = AsyncMock(return_value=[])
    repo.supersede_challenges = AsyncMock()
    challenge = MagicMock()
    challenge.id = uuid.uuid4()
    challenge.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    challenge.user_id = None
    repo.insert_pending_challenge = AsyncMock(return_value=challenge)
    service._repo = repo
    return service, repo, challenge


@pytest.mark.asyncio
async def test_challenge_winner_inserts_pending_decoy() -> None:
    service, repo, challenge = _winner_service()
    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip="127.0.0.1",
    )
    assert result.kind == "accepted"
    assert result.http_status == 202
    assert result.challenge_id == challenge.id
    repo.insert_pending_challenge.assert_awaited_once()
    kwargs = repo.insert_pending_challenge.await_args.kwargs
    assert kwargs["user_id"] is None
    assert kwargs["phone_normalized"] == _FIXED_PHONE
    assert "code" not in kwargs


@pytest.mark.asyncio
async def test_challenge_cooldown_reuses_latest_handle() -> None:
    service, repo, _challenge = _winner_service()
    latest = MagicMock()
    latest.id = uuid.uuid4()
    latest.created_at = datetime.now()  # naive → _ensure_aware
    latest.expires_at = datetime.now() + timedelta(minutes=5)
    latest.state = "pending_delivery"
    latest.user_id = None
    repo.lock_latest_challenges_for_phone = AsyncMock(return_value=[latest])
    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip="127.0.0.1",
    )
    assert result.kind == "accepted"
    assert result.challenge_id == latest.id
    repo.insert_pending_challenge.assert_not_awaited()
    event = repo.append_security_event.await_args.kwargs
    assert event["reason_code"] == "cooldown_reuse"


@pytest.mark.asyncio
async def test_challenge_supersedes_dispatching_latest() -> None:
    service, repo, challenge = _winner_service()
    dispatching = MagicMock()
    dispatching.id = uuid.uuid4()
    dispatching.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    dispatching.expires_at = datetime.now(timezone.utc)
    dispatching.state = "dispatching"
    dispatching.user_id = None
    repo.lock_latest_challenges_for_phone = AsyncMock(return_value=[dispatching])
    repo.lock_current_challenges_for_phone = AsyncMock(return_value=[dispatching])
    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
        client_ip="127.0.0.1",
    )
    assert result.kind == "accepted"
    assert result.challenge_id == challenge.id
    assert repo.supersede_challenges.await_count >= 1


@pytest.mark.asyncio
async def test_idempotency_replay_parses_iso_datetimes() -> None:
    settings = _settings()
    record = _record(settings)
    record.state = "succeeded"
    record.result_code = "0"
    record.http_status = 202
    record.result_payload = {
        "challenge_id": str(uuid.uuid4()),
        "phone_masked": "138****8000",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "resend_available_at": "2030-01-01T00:01:00+00:00",
    }
    service = ChallengeService(AsyncMock(), settings, provider_health_ok=True)
    repo = AsyncMock()
    repo.try_begin_idempotency = AsyncMock(return_value=(record, False))
    service._repo = repo
    result = await service.request_challenge(
        phone=_FIXED_PHONE,
        idempotency_key=_FIXED_IDEMPOTENCY_KEY,
        request_id=_FIXED_REQUEST_ID,
    )
    assert result.kind == "replay"
    assert isinstance(result.data["expires_at"], datetime)


def _delivery() -> tuple[DeliveryService, AsyncMock, AsyncMock]:
    sms = AsyncMock()
    sms.send = AsyncMock(return_value=SmsDeliveryResult.accepted("ref"))
    sms.query_status = AsyncMock(return_value=None)
    service = DeliveryService(AsyncMock(), _settings(), sms)
    repo = AsyncMock()
    repo.rollback = AsyncMock()
    repo.commit = AsyncMock()
    repo.append_security_event = AsyncMock()
    repo.finalize_delivered = AsyncMock()
    repo.finalize_delivery_failed = AsyncMock()
    repo.mark_send_started = AsyncMock(return_value=True)
    repo.lock_user_by_id = AsyncMock(return_value=None)
    repo.is_auth_eligible = MagicMock(return_value=False)
    service._repo = repo
    return service, repo, sms


@pytest.mark.asyncio
async def test_delivery_decoy_without_registration_phone() -> None:
    service, repo, _sms = _delivery()
    cid = uuid.uuid4()
    challenge = SimpleNamespace(id=cid, user_id=None, phone_normalized=None)
    locked = SimpleNamespace(id=cid, state="pending_delivery", phone_ref=b"x")
    repo.lock_challenge = AsyncMock(return_value=locked)
    out = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone=None
    )
    assert out.provider_outcome == "decoy_delivered"
    assert out.sent is False


@pytest.mark.asyncio
async def test_delivery_decoy_missing_lock() -> None:
    service, repo, _sms = _delivery()
    cid = uuid.uuid4()
    challenge = SimpleNamespace(id=cid, user_id=None, phone_normalized=None)
    repo.lock_challenge = AsyncMock(return_value=None)
    out = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone=None
    )
    assert out.provider_outcome == "skipped_state"


@pytest.mark.asyncio
async def test_delivery_missing_challenge_and_ineligible_user() -> None:
    service, repo, _sms = _delivery()
    cid = uuid.uuid4()
    uid = uuid.uuid4()
    challenge = SimpleNamespace(id=cid, user_id=uid, phone_normalized="13800138000")
    repo.lock_challenge = AsyncMock(return_value=None)
    missing = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone="13800138000"
    )
    assert missing.provider_outcome == "missing"
    locked = SimpleNamespace(
        id=cid,
        state="pending_delivery",
        provider_request_ref=uuid.uuid4(),
        code_key_version=1,
        expires_at=datetime.now(timezone.utc),
    )
    repo.lock_challenge = AsyncMock(return_value=locked)
    ineligible = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone="13800138000"
    )
    assert ineligible.provider_outcome == "user_ineligible"


@pytest.mark.asyncio
async def test_delivery_missing_destination_lease_lost_and_timeout() -> None:
    service, repo, sms = _delivery()
    cid = uuid.uuid4()
    uid = uuid.uuid4()
    challenge = SimpleNamespace(id=cid, user_id=uid, phone_normalized="13800138000")
    locked = SimpleNamespace(
        id=cid,
        state="pending_delivery",
        provider_request_ref=uuid.uuid4(),
        code_key_version=1,
        expires_at=datetime.now(),  # naive
    )
    repo.lock_challenge = AsyncMock(return_value=locked)
    repo.is_auth_eligible = MagicMock(return_value=True)
    repo.lock_user_by_id = AsyncMock(return_value=SimpleNamespace(id=uid))
    missing_dest = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone=None
    )
    assert missing_dest.provider_outcome == "missing_destination"
    repo.mark_send_started = AsyncMock(return_value=False)
    lease = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone="13800138000"
    )
    assert lease.provider_outcome == "lease_lost"
    repo.mark_send_started = AsyncMock(return_value=True)
    sms.send = AsyncMock(side_effect=TimeoutError())
    timed = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone="13800138000"
    )
    assert timed.sent is True
    sms.send = AsyncMock(side_effect=RuntimeError("boom"))
    unknown = await service.prepare_and_send(
        challenge, owner="disp", request_id="r", destination_phone="13800138000"
    )
    assert unknown.sent is True


@pytest.mark.asyncio
async def test_finalize_and_invalidate_recovery_paths() -> None:
    service, repo, sms = _delivery()
    cid = uuid.uuid4()
    repo.lock_challenge = AsyncMock(return_value=None)
    missing = await service.finalize_result(
        cid, result=SmsDeliveryResult.accepted("r"), request_id="r"
    )
    assert missing.provider_outcome == "missing"
    repo.lock_challenge = AsyncMock(
        return_value=SimpleNamespace(id=cid, state="delivered")
    )
    already = await service.finalize_result(
        cid, result=SmsDeliveryResult.accepted("r"), request_id="r"
    )
    assert already.provider_outcome == "already_final"
    repo.get_challenge = AsyncMock(return_value=None)
    gone = await service.invalidate_after_send_started(cid, request_id="r")
    assert gone.provider_outcome == "missing"
    ch = SimpleNamespace(id=cid, user_id=None, provider_request_ref=uuid.uuid4())
    repo.get_challenge = AsyncMock(return_value=ch)
    sms.query_status = AsyncMock(return_value=None)
    repo.lock_challenge = AsyncMock(
        return_value=SimpleNamespace(id=cid, state="dispatching")
    )
    failed = await service.invalidate_after_send_started(cid, request_id="r")
    assert failed.state == "delivery_failed"
    await service._fail_after_send_started(
        cid, request_id="r", outcome="configuration_invalid"
    )
    repo.lock_challenge = AsyncMock(return_value=None)
    await service._fail_after_send_started(
        cid, request_id="r", outcome="configuration_invalid"
    )
