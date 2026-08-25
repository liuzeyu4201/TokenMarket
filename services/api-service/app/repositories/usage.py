"""Sync SQLAlchemy adapter for usage logs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.usage.models import UsageConflict, UsageLog
from app.domain.usage.service import UsageRecord


def _to_rec(row: UsageLog) -> UsageRecord:
    return UsageRecord(
        request_id=row.request_id,
        buyer_id=row.buyer_id,
        platform=row.platform,
        model=row.model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        status="complete" if row.usage_source == "official" else "missing",
        source=row.usage_source,
        proxy_key_id=row.proxy_key_id,
        api_key_id=row.api_key_id,
        seller_id=row.seller_id,
        partial=row.partial,
        latency_ms=row.latency_ms,
        status_code=row.status_code,
        end_reason=row.end_reason,
    )


class SQLUsageStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, request_id: str) -> UsageRecord | None:
        row = self._s.execute(
            select(UsageLog).where(UsageLog.request_id == request_id)
        ).scalar_one_or_none()
        return _to_rec(row) if row is not None else None

    def insert(self, rec: UsageRecord) -> None:
        self._s.add(
            UsageLog(
                usage_id=uuid.uuid4(),
                request_id=rec.request_id,
                proxy_key_id=rec.proxy_key_id,
                api_key_id=rec.api_key_id,
                buyer_id=rec.buyer_id,
                seller_id=rec.seller_id,
                platform=rec.platform,
                model=rec.model,
                prompt_tokens=rec.prompt_tokens,
                completion_tokens=rec.completion_tokens,
                total_tokens=rec.total_tokens,
                usage_source=rec.source,
                partial=rec.partial,
                latency_ms=rec.latency_ms,
                status_code=rec.status_code,
                end_reason=rec.end_reason or rec.status,
                created_at=datetime.now(timezone.utc),
            )
        )
        self._s.flush()

    def add_conflict(self, request_id: str, reason: str) -> None:
        self._s.add(
            UsageConflict(
                id=uuid.uuid4(),
                request_id=request_id,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
        )
