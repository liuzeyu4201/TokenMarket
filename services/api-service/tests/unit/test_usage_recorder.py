"""SF17 usage records must not fake zeros."""

from __future__ import annotations

import uuid

import pytest

from app.domain.proxykeys.models import ProxyKey
from app.domain.usage.models import UsageLog
from app.domain.usage.service import UsageRecord, UsageRecorder


def test_orm_tables_named() -> None:
    assert ProxyKey.__tablename__ == "proxy_keys"
    assert UsageLog.__tablename__ == "usage_logs"


def test_missing_cannot_store_zeros() -> None:
    r = UsageRecorder()
    with pytest.raises(ValueError):
        r.record(
            UsageRecord(
                request_id="r",
                buyer_id=uuid.uuid4(),
                platform="volcano",
                model="doubao-pro-32k",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                status="missing",
                source="upstream",
            )
        )


def test_failed_may_store_zero_tokens() -> None:
    r = UsageRecorder()
    r.record(
        UsageRecord(
            request_id="fail",
            buyer_id=None,
            platform="volcano",
            model="m",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            status="failed",
            source="not_available",
        )
    )
    assert r.rows[0].source == "not_available"


def test_idempotent_same_request_id() -> None:
    r = UsageRecorder()
    rec = UsageRecord(
        request_id="same",
        buyer_id=None,
        platform="volcano",
        model="m",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        status="complete",
        source="official",
    )
    r.record(rec)
    r.record(rec)
    assert len(r.rows) == 1


def test_purge_older_than_30_days() -> None:
    from datetime import datetime, timedelta, timezone

    r = UsageRecorder()
    rec = UsageRecord(
        request_id="old",
        buyer_id=None,
        platform="volcano",
        model="m",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        status="complete",
        source="official",
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    r.record(rec)
    r.record(
        UsageRecord(
            request_id="fresh",
            buyer_id=None,
            platform="volcano",
            model="m",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            status="complete",
            source="official",
        )
    )
    n = r.purge_expired(now=datetime.now(timezone.utc), retain_days=30)
    assert n == 1
    assert r._store.get("old") is None
    assert r._store.get("fresh") is not None


def test_complete_stored() -> None:
    r = UsageRecorder()
    r.record(
        UsageRecord(
            request_id="r",
            buyer_id=None,
            platform="volcano",
            model="m",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            status="complete",
            source="upstream",
        )
    )
    assert r.rows[0].total_tokens == 3
