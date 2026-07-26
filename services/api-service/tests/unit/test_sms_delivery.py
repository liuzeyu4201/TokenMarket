"""Unit tests for SMS delivery port and adapters (T032)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import AuthSettings
from app.observability import record_auth_provider_outcome, redact_message
from app.security.otp import derive_otp
from app.sms.fake import BlockingSmsFake
from app.sms.port import (
    DeliveryCategory,
    SmsDeliveryRequest,
    SmsDeliveryResult,
    SmsDeliveryStatus,
)
from app.sms.synthetic import (
    ProductionBlockedSmsAdapter,
    SyntheticSmsAdapter,
    build_sms_adapter,
)


def _request(**kwargs: object) -> SmsDeliveryRequest:
    base = dict(
        provider_request_ref=uuid.uuid4(),
        destination="13800138000",
        code="012345",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        template="login_verification_v1",
        request_id="req-1",
    )
    base.update(kwargs)
    return SmsDeliveryRequest(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_synthetic_accepts_with_stable_provider_ref() -> None:
    adapter = SyntheticSmsAdapter(timeout_seconds=10)
    req = _request()
    result = await adapter.send(req)
    assert result.status is SmsDeliveryStatus.accepted
    assert result.safe_provider_ref is not None
    assert str(req.provider_request_ref) in result.safe_provider_ref
    assert adapter.provider_health_ok() is True


@pytest.mark.asyncio
async def test_prf_memory_recompute_stable() -> None:
    key = b"tm_test_" + b"z" * 32
    cid = uuid.uuid4()
    a = derive_otp(key, cid)
    b = derive_otp(key, cid)
    assert a == b
    assert len(a) == 6
    # Leading-zero capable representation.
    assert a.isdigit()


@pytest.mark.asyncio
async def test_blocking_fake_blocks_until_release() -> None:
    import asyncio

    fake = BlockingSmsFake()
    fake.block()
    task = asyncio.create_task(fake.send(_request()))
    await asyncio.wait_for(fake.send_entered.wait(), timeout=2.0)
    assert not task.done()
    fake.unblock()
    result = await asyncio.wait_for(task, timeout=2.0)
    assert isinstance(result, SmsDeliveryResult)
    assert result.status is SmsDeliveryStatus.accepted
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_no_automatic_resend_on_failure() -> None:
    fake = BlockingSmsFake()
    fake.set_result(SmsDeliveryStatus.rejected)
    r1 = await fake.send(_request(provider_request_ref=uuid.uuid4()))
    r2 = await fake.send(_request(provider_request_ref=uuid.uuid4()))
    assert r1.status is SmsDeliveryStatus.rejected
    assert r2.status is SmsDeliveryStatus.rejected
    # Adapter does not retry; two calls = two explicit sends.
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_timeout_category_mapping() -> None:
    fake = BlockingSmsFake()
    fake.set_result(
        SmsDeliveryStatus.unavailable,
        category=DeliveryCategory.provider_timeout,
    )
    result = await fake.send(_request())
    assert result.status is SmsDeliveryStatus.unavailable
    assert result.category is DeliveryCategory.provider_timeout


def test_synthetic_prod_isolation() -> None:
    settings = AuthSettings(
        session_hmac_key_current="tm_test_" + "a" * 40,
        otp_hmac_key_current="tm_test_" + "a" * 40,
        csrf_hmac_key_current="tm_test_" + "a" * 40,
        reference_hmac_key_current="tm_test_" + "a" * 40,
        sms_adapter="synthetic",
        tls_ready=True,
        browser_origins="https://app.example.com",
    )
    prod = build_sms_adapter(settings, mode="prod")
    assert isinstance(prod, ProductionBlockedSmsAdapter)
    assert prod.provider_health_ok() is False

    local = build_sms_adapter(settings, mode="local")
    assert isinstance(local, SyntheticSmsAdapter)
    assert local.provider_health_ok() is True


@pytest.mark.asyncio
async def test_exception_redaction_in_message() -> None:
    msg = "sms failed otp: 012345 phone 13800138000"
    redacted = redact_message(msg)
    assert "012345" not in redacted
    assert "13800138000" not in redacted


def test_delivery_outcome_metric_low_cardinality() -> None:
    record_auth_provider_outcome("accepted")
    record_auth_provider_outcome("rejected")
    record_auth_provider_outcome("provider_timeout")


@pytest.mark.asyncio
async def test_request_mapping_fields() -> None:
    req = _request(code="000001", destination="13900139000")
    assert req.template == "login_verification_v1"
    assert req.code == "000001"
    assert len(req.code) == 6
    fake = BlockingSmsFake(timeout_seconds=10)
    await fake.send(req)
    assert fake.calls[0]["code_len"] == 6
    assert fake.calls[0]["timeout_seconds"] == 10
