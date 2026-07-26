"""Integration: SMS delivery outcomes and send_started recovery (T059 / US2)."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import timedelta
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import AuthSettings, clear_auth_settings_cache
from app.dependencies import create_session_engine
from app.dispatch.auth_delivery import AuthDeliveryDispatcher
from app.domain.authentication.models import VerificationRequestIdempotencyRecord
from app.repositories.authentication import (
    IDEMPOTENCY_DELETE_BUFFER,
    IDEMPOTENCY_REPLAY,
    AuthenticationRepository,
    utc_now,
)
from app.security.otp import derive_otp, generate_code_salt, otp_verification_digest
from app.security.reference import phone_ref
from app.sms.fake import BlockingSmsFake
from app.sms.port import DeliveryCategory, SmsDeliveryStatus

pytestmark = pytest.mark.integration

_KEY = "tm_smsrec_" + secrets.token_urlsafe(32)


def _settings() -> AuthSettings:
    return AuthSettings(
        session_hmac_key_current=_KEY,
        otp_hmac_key_current=_KEY,
        csrf_hmac_key_current=_KEY,
        reference_hmac_key_current=_KEY,
        browser_origins="https://127.0.0.1:5173",
        sms_adapter="fake",
        dispatcher_lease_seconds=2,
        dispatcher_batch_size=10,
        dispatcher_drain_seconds=1,
    )


@pytest.fixture
def recovery_env(
    auth_migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, AuthSettings]]:
    monkeypatch.setenv("DATABASE_URL", auth_migrated_postgres)
    monkeypatch.setenv("MODE", "local")
    monkeypatch.setenv("AUTH_SESSION_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_OTP_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_CSRF_HMAC_KEY_CURRENT", _KEY)
    monkeypatch.setenv("AUTH_REFERENCE_HMAC_KEY_CURRENT", _KEY)
    clear_auth_settings_cache()
    yield auth_migrated_postgres, _settings()
    clear_auth_settings_cache()


async def _insert_pending(
    factory: async_sessionmaker[AsyncSession],
    settings: AuthSettings,
    *,
    phone: str,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    async with factory() as session:
        repo = AuthenticationRepository(session)
        now = utc_now()
        ref_mat = settings.key_material("reference")
        otp_mat = settings.key_material("otp")
        p_ref = phone_ref(ref_mat.current, phone)
        idem = VerificationRequestIdempotencyRecord(
            id=uuid.uuid4(),
            operation="request_verification_code",
            key_digest=secrets.token_bytes(32),
            key_version=ref_mat.version,
            phone_ref=p_ref,
            state="processing",
            created_at=now,
            replay_until=now + IDEMPOTENCY_REPLAY,
            delete_after=now + IDEMPOTENCY_DELETE_BUFFER,
        )
        session.add(idem)
        await session.flush()

        cid = uuid.uuid4()
        code = derive_otp(otp_mat.current, cid)
        salt = generate_code_salt()
        digest = otp_verification_digest(otp_mat.current, cid, salt, code)
        await repo.insert_pending_challenge(
            challenge_id=cid,
            user_id=user_id,
            idempotency_record_id=idem.id,
            phone_ref=p_ref,
            code_digest=digest,
            code_salt=salt,
            code_key_version=otp_mat.version,
            provider_request_ref=uuid.uuid4(),
            now=now,
        )
        await repo.complete_idempotency(
            idem,
            http_status=202,
            result_code="0",
            result_payload={"challenge_id": str(cid)},
            now=now,
        )
        await session.commit()
        return cid


@pytest.mark.parametrize(
    "outcome,expected_state",
    [
        (SmsDeliveryStatus.accepted, "delivered"),
        (SmsDeliveryStatus.rejected, "delivery_failed"),
        (SmsDeliveryStatus.unavailable, "delivery_failed"),
        (SmsDeliveryStatus.unknown, "delivery_failed"),
    ],
)
def test_recipient_outcomes_finalize(
    recovery_env: tuple[str, AuthSettings],
    account_factory,
    outcome: SmsDeliveryStatus,
    expected_state: str,
) -> None:
    url, settings = recovery_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()
    fake.set_result(outcome, category=DeliveryCategory.provider_rejected)

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="out")
        await d.run_once()
        sync = create_engine(url, pool_pre_ping=True)
        try:
            with sync.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT state, code_digest FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": str(cid)},
                ).one()
            assert row[0] == expected_state
            if expected_state == "delivery_failed":
                assert row[1] is None  # OTP material cleared
            else:
                assert row[1] is not None
        finally:
            sync.dispose()
        assert len(fake.calls) == 1

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_send_started_crash_never_resends(
    recovery_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = recovery_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        async with factory() as session:
            repo = AuthenticationRepository(session)
            ch = await repo.lock_challenge(cid)
            assert ch is not None
            ch.dispatch_lease_owner = "crashed"
            ch.dispatch_lease_until = utc_now() + timedelta(seconds=30)
            ok = await repo.mark_send_started(ch, owner="crashed")
            assert ok
            ch.send_started_at = utc_now() - timedelta(seconds=60)
            await session.commit()

        calls_before = len(fake.calls)
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="recover")
        recovered = await d.recover_stale_dispatching()
        assert recovered >= 1
        assert len(fake.calls) == calls_before  # never resend

        # Process path also must not resend
        await d.run_once()
        assert len(fake.calls) == calls_before

        sync = create_engine(url, pool_pre_ping=True)
        try:
            with sync.connect() as conn:
                state = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": str(cid)},
                ).scalar_one()
            assert state == "delivery_failed"
        finally:
            sync.dispose()

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_query_status_recovers_accepted_without_resend(
    recovery_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = recovery_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()
    # Pretend prior send was accepted — query_status will report it.
    fake.set_result(SmsDeliveryStatus.accepted)

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        async with factory() as session:
            repo = AuthenticationRepository(session)
            ch = await repo.lock_challenge(cid)
            assert ch is not None
            provider_ref = ch.provider_request_ref
            ch.dispatch_lease_owner = "crashed"
            ok = await repo.mark_send_started(ch, owner="crashed")
            assert ok
            ch.send_started_at = utc_now() - timedelta(seconds=60)
            await session.commit()

        # Seed fake call log so query_status finds the ref
        fake.calls.append(
            {
                "provider_request_ref": provider_ref,
                "code_len": 6,
                "destination_ref": None,
                "timeout_seconds": 10,
            }
        )
        calls_before = len(fake.calls)
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="query")
        await d.recover_stale_dispatching()
        # No additional send
        assert len(fake.calls) == calls_before

        sync = create_engine(url, pool_pre_ping=True)
        try:
            with sync.connect() as conn:
                state = conn.execute(
                    text(
                        "SELECT state FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": str(cid)},
                ).scalar_one()
            assert state == "delivered"
        finally:
            sync.dispose()

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_unsupported_query_invalidates(
    recovery_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = recovery_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        async with factory() as session:
            repo = AuthenticationRepository(session)
            ch = await repo.lock_challenge(cid)
            assert ch is not None
            ch.dispatch_lease_owner = "crashed"
            ok = await repo.mark_send_started(ch, owner="crashed")
            assert ok
            ch.send_started_at = utc_now() - timedelta(seconds=60)
            await session.commit()

        # query_status returns None (no prior call) → invalidate
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="inv")
        await d.recover_stale_dispatching()
        assert len(fake.calls) == 0
        sync = create_engine(url, pool_pre_ping=True)
        try:
            with sync.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT state, code_digest FROM verification_challenges "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": str(cid)},
                ).one()
            assert row[0] == "delivery_failed"
            assert row[1] is None
        finally:
            sync.dispose()

    asyncio.run(_run())
    asyncio.run(engine.dispose())
