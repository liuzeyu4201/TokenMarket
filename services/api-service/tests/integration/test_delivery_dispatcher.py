"""Integration: delivery dispatcher claim/lease/recovery (T035)."""

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
from app.repositories.authentication import AuthenticationRepository, utc_now
from app.security.otp import derive_otp, generate_code_salt, otp_verification_digest
from app.security.reference import phone_ref
from app.sms.fake import BlockingSmsFake

pytestmark = pytest.mark.integration

_KEY = "tm_dispatch_" + secrets.token_urlsafe(32)


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
def dispatch_env(
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
        from app.domain.authentication.models import (
            VerificationRequestIdempotencyRecord,
        )
        from app.repositories.authentication import (
            IDEMPOTENCY_DELETE_BUFFER,
            IDEMPOTENCY_REPLAY,
        )

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


def test_concurrent_dispatchers_single_claim(
    dispatch_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = dispatch_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        d1 = AuthDeliveryDispatcher(factory, settings, fake, owner="d1")
        d2 = AuthDeliveryDispatcher(factory, settings, fake, owner="d2")
        # Claim concurrently
        r1, r2 = await asyncio.gather(d1.run_once(), d2.run_once())
        assert r1 + r2 == 1
        # Only one send
        assert len(fake.calls) == 1
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


def test_lease_expiry_pre_send_recovery(
    dispatch_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = dispatch_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        # Manually claim with expired lease, pre-send
        async with factory() as session:
            repo = AuthenticationRepository(session)
            claimed = await repo.claim_pending_batch(
                owner="stale-owner",
                lease_seconds=1,
                batch_size=5,
            )
            assert len(claimed) == 1
            # Force lease into the past without send_started
            claimed[0].dispatch_lease_until = utc_now() - timedelta(seconds=5)
            await session.commit()

        d = AuthDeliveryDispatcher(factory, settings, fake, owner="recover")
        n = await d.run_once()
        assert n == 1
        assert len(fake.calls) == 1
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


def test_send_started_no_resend_query_or_invalidate(
    dispatch_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = dispatch_env
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
            # Age past lease window so recovery selects this row.
            ch.send_started_at = utc_now() - timedelta(seconds=30)
            await session.commit()

        calls_before = len(fake.calls)
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="recover2")
        recovered = await d.recover_stale_dispatching()
        assert recovered >= 1
        # No additional send (send_started already set)
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
            # Invalidated without resend (query returns None — never sent)
            assert state == "delivery_failed"
        finally:
            sync.dispose()

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_graceful_stop_and_one_send_per_provider_ref(
    dispatch_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = dispatch_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        cid = await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        d = AuthDeliveryDispatcher(
            factory, settings, fake, owner="stop-test", poll_interval_seconds=0.05
        )
        d.start()
        # Wait until delivered
        sync = create_engine(url, pool_pre_ping=True)
        try:
            for _ in range(50):
                with sync.connect() as conn:
                    state = conn.execute(
                        text(
                            "SELECT state FROM verification_challenges "
                            "WHERE id = CAST(:id AS uuid)"
                        ),
                        {"id": str(cid)},
                    ).scalar_one()
                if state == "delivered":
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError("not delivered")
        finally:
            sync.dispose()

        await d.stop(drain_seconds=1.0)
        assert not d.running
        assert len(fake.calls) == 1
        refs = {c["provider_request_ref"] for c in fake.calls}
        assert len(refs) == 1

        # Second run must not resend
        n = await d.run_once()  # stop is set — should no-op
        assert n == 0
        assert len(fake.calls) == 1

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def test_provider_ref_at_most_one_send_even_if_run_twice(
    dispatch_env: tuple[str, AuthSettings],
    account_factory,
) -> None:
    url, settings = dispatch_env
    user = account_factory.create_active()
    engine = create_session_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fake = BlockingSmsFake()

    async def _run() -> None:
        await _insert_pending(
            factory, settings, phone=user.phone_normalized, user_id=user.id
        )
        d = AuthDeliveryDispatcher(factory, settings, fake, owner="once")
        await d.run_once()
        await d.run_once()
        assert len(fake.calls) == 1

    asyncio.run(_run())
    asyncio.run(engine.dispose())
