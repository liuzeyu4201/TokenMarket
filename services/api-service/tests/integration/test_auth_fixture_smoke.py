"""Smoke test for authentication fixtures (T009).

Verifies pytest collection, fixture resolution, PostgreSQL/Redis versions and
lifecycle, account factories, DB clock, and blocking SMS fake.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import redis
from sqlalchemy import text

from tests.integration.conftest_authentication import (
    AccountFactory,
    AuthPostgresHandle,
    AuthRedisHandle,
    BlockingSmsFake,
    ControllableDbClock,
    DispatcherStub,
)

pytestmark = pytest.mark.integration


def test_auth_postgres_version_and_lifecycle(
    auth_postgres_container: AuthPostgresHandle,
) -> None:
    engine = auth_postgres_container.engine()
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
            assert isinstance(version, str)
            assert version.startswith("15.18"), f"expected PG 15.18, got {version!r}"
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()

    # stop / start cycle proves lifecycle control
    auth_postgres_container.stop()
    auth_postgres_container.start()
    engine = auth_postgres_container.engine()
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_auth_redis_version_and_lifecycle(
    auth_redis_container: AuthRedisHandle,
) -> None:
    client = redis.Redis(
        host=auth_redis_container.host,
        port=auth_redis_container.port,
        decode_responses=True,
    )
    try:
        assert client.ping() is True
        info = client.info("server")
        redis_version = str(info.get("redis_version", ""))
        assert redis_version.startswith(
            "7.2"
        ), f"expected Redis 7.2.x, got {redis_version!r}"
        client.set("tm:smoke:key", "1", ex=10)
        assert client.get("tm:smoke:key") == "1"
    finally:
        client.close()

    auth_redis_container.stop()
    auth_redis_container.start()
    client = redis.Redis(
        host=auth_redis_container.host,
        port=auth_redis_container.port,
        decode_responses=True,
    )
    try:
        assert client.ping() is True
    finally:
        client.close()


def test_db_clock_reads_server_time(db_clock: ControllableDbClock) -> None:
    now = db_clock.db_now()
    assert now.tzinfo is not None
    from datetime import timedelta, timezone

    # Controllable offset does not require freezegun
    db_clock.advance(timedelta(minutes=5))
    advanced = db_clock.db_now()
    assert advanced - now >= timedelta(minutes=4, seconds=50)
    db_clock.set_offset(timedelta(0))
    reset = db_clock.db_now()
    assert abs((reset - now).total_seconds()) < 30
    # silence unused import if timezone used only for docs
    assert timezone.utc is not None


def test_account_factory_four_kinds(account_factory: AccountFactory) -> None:
    active = account_factory.create_active()
    assert active.status.value == "active"
    assert active.is_deleted is False
    assert active.phone_normalized

    suspended = account_factory.create_suspended()
    assert suspended.status.value == "suspended"
    assert suspended.is_deleted is False

    deleted = account_factory.create_deleted()
    assert deleted.is_deleted is True

    unknown = account_factory.unknown_phone()
    assert len(unknown) == 11
    assert unknown.startswith("1")
    assert unknown not in {
        active.phone_normalized,
        suspended.phone_normalized,
        deleted.phone_normalized,
    }


@pytest.mark.asyncio
async def test_blocking_sms_fake_and_dispatcher(
    blocking_sms_fake: BlockingSmsFake,
    dispatcher_stub: DispatcherStub,
) -> None:
    blocking_sms_fake.block()
    ref = uuid.uuid4()
    task = asyncio.create_task(
        blocking_sms_fake.send(
            destination_ref=b"\x01\x02",
            code="123456",
            provider_request_ref=ref,
        )
    )
    await asyncio.wait_for(blocking_sms_fake.send_entered.wait(), timeout=2.0)
    assert not task.done()
    blocking_sms_fake.unblock()
    result = await asyncio.wait_for(task, timeout=2.0)
    assert result == "accepted"
    assert len(blocking_sms_fake.calls) == 1
    assert blocking_sms_fake.calls[0]["provider_request_ref"] == ref

    cid = uuid.uuid4()
    dispatcher_stub.record_claim(cid)
    dispatcher_stub.record_finalize(cid, "delivered")
    assert dispatcher_stub.claimed == [cid]
    assert dispatcher_stub.finalized == [(cid, "delivered")]
    assert dispatcher_stub.owner.startswith("test-dispatcher-")


def test_auth_env_sets_urls(
    auth_env: dict[str, str],
) -> None:
    import os

    assert os.environ["DATABASE_URL"] == auth_env["DATABASE_URL"]
    assert os.environ["REDIS_URL"] == auth_env["REDIS_URL"]
    assert auth_env["DATABASE_URL"].startswith("postgresql://")
    assert auth_env["REDIS_URL"].startswith("redis://")
