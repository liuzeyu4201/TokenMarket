"""Sync SQLAlchemy adapter for seller API keys (used via AsyncSession.run_sync)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.sellerkeys.lifecycle import has_positive_quota, routable
from app.domain.sellerkeys.models import SellerAPIKey, SellerKeyIdempotency


def _row_to_dict(row: SellerAPIKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "seller_id": row.seller_id,
        "platform": row.platform,
        "fingerprint": row.fingerprint,
        "masked_hint": row.masked_hint,
        "ciphertext": row.ciphertext,
        "nonce": row.nonce,
        "tag": row.tag,
        "key_version": row.key_version,
        "remaining_quota": row.remaining_quota,
        "quota_unit": row.quota_unit,
        "administrative_state": row.administrative_state,
        "health_state": row.health_state,
        "last_validated_at": row.last_validated_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_request_id": row.created_request_id,
        "version": row.version,
        "soft_deleted": row.soft_deleted,
    }


class SQLKeyStore:
    def __init__(self, session: Session) -> None:
        self._s = session

    def find_by_fingerprint(self, platform: str, fingerprint: str) -> uuid.UUID | None:
        got = self._s.execute(
            select(SellerAPIKey.id).where(
                SellerAPIKey.platform == platform,
                SellerAPIKey.fingerprint == fingerprint,
                SellerAPIKey.soft_deleted.is_(False),
            )
        ).scalar_one_or_none()
        return got

    def insert(self, record: dict[str, Any]) -> uuid.UUID:
        now = datetime.now(timezone.utc)
        row = SellerAPIKey(
            id=record["id"],
            seller_id=record["seller_id"],
            platform=record["platform"],
            fingerprint=record["fingerprint"],
            masked_hint=record["masked_hint"],
            ciphertext=record.get("ciphertext"),
            nonce=record.get("nonce"),
            tag=record.get("tag"),
            key_version=record["key_version"],
            remaining_quota=record.get("remaining_quota"),
            quota_unit=record.get("quota_unit"),
            administrative_state=record.get("administrative_state") or "active",
            health_state=record.get("health_state") or "unknown",
            last_validated_at=record.get("last_validated_at"),
            created_at=now,
            updated_at=now,
            created_request_id=record["created_request_id"],
            version=1,
            soft_deleted=False,
        )
        self._s.add(row)
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ValueError("duplicate") from exc
        return row.id

    def get_idempotency(self, key: str) -> tuple[str, uuid.UUID | None] | None:
        row = self._s.get(SellerKeyIdempotency, key)
        if row is None:
            return None
        return row.request_hash, row.result_key_id

    def put_idempotency(
        self,
        key: str,
        seller_id: uuid.UUID,
        digest: str,
        code: str,
        key_id: uuid.UUID | None,
    ) -> None:
        existing = self._s.get(SellerKeyIdempotency, key)
        if existing is not None:
            existing.request_hash = digest
            existing.result_code = code
            existing.result_key_id = key_id
            return
        self._s.add(
            SellerKeyIdempotency(
                idempotency_key=key,
                seller_id=seller_id,
                request_hash=digest,
                result_key_id=key_id,
                result_code=code,
                created_at=datetime.now(timezone.utc),
            )
        )

    def get(self, key_id: uuid.UUID) -> dict[str, Any] | None:
        row = self._s.get(SellerAPIKey, key_id)
        if row is None or row.soft_deleted:
            return None
        return _row_to_dict(row)

    def list_by_seller(self, seller_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self._s.execute(
            select(SellerAPIKey).where(
                SellerAPIKey.seller_id == seller_id,
                SellerAPIKey.soft_deleted.is_(False),
            )
        ).scalars()
        return [_row_to_dict(r) for r in rows]

    def save(self, record: dict[str, Any]) -> None:
        row = self._s.get(SellerAPIKey, record["id"])
        if row is None:
            return
        row.administrative_state = str(
            record.get("administrative_state") or row.administrative_state
        )
        row.health_state = str(record.get("health_state") or row.health_state)
        row.remaining_quota = record.get("remaining_quota")
        row.quota_unit = record.get("quota_unit")
        row.last_validated_at = record.get("last_validated_at")
        row.ciphertext = record.get("ciphertext")
        row.nonce = record.get("nonce")
        row.tag = record.get("tag")
        row.version = int(record.get("version") or row.version)
        row.updated_at = datetime.now(timezone.utc)
        row.soft_deleted = bool(record.get("soft_deleted") or False)

    def list_routable(self) -> list[dict[str, Any]]:
        rows = self._s.execute(
            select(SellerAPIKey).where(SellerAPIKey.soft_deleted.is_(False))
        ).scalars()
        return [
            _row_to_dict(r)
            for r in rows
            if routable(r.administrative_state, r.health_state)
            and has_positive_quota(r.remaining_quota)
            and r.ciphertext
        ]

    def apply_health(self, key_id: uuid.UUID, health: str) -> None:
        row = self._s.get(SellerAPIKey, key_id)
        if row is None:
            return
        row.health_state = health
        row.updated_at = datetime.now(timezone.utc)
