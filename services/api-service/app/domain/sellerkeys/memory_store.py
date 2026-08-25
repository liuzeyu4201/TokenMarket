"""In-memory KeyStore for unit tests."""

from __future__ import annotations

import uuid
from typing import Any


class MemoryKeyStore:
    def __init__(self) -> None:
        self.by_fp: dict[tuple[str, str], uuid.UUID] = {}
        self.rows: dict[uuid.UUID, dict[str, Any]] = {}
        self.idem: dict[str, tuple[str, uuid.UUID | None]] = {}

    def find_by_fingerprint(self, platform: str, fingerprint: str) -> uuid.UUID | None:
        return self.by_fp.get((platform, fingerprint))

    def insert(self, record: dict[str, Any]) -> uuid.UUID:
        key_id: uuid.UUID = record["id"]
        if (record["platform"], record["fingerprint"]) in self.by_fp:
            raise ValueError("duplicate")
        self.by_fp[(record["platform"], record["fingerprint"])] = key_id
        self.rows[key_id] = dict(record)
        return key_id

    def get_idempotency(self, key: str) -> tuple[str, uuid.UUID | None] | None:
        return self.idem.get(key)

    def put_idempotency(
        self,
        key: str,
        seller_id: uuid.UUID,
        digest: str,
        code: str,
        key_id: uuid.UUID | None,
    ) -> None:
        self.idem[key] = (digest, key_id)

    def get(self, key_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.rows.get(key_id)
        return dict(row) if row is not None else None

    def list_by_seller(self, seller_id: uuid.UUID) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.rows.values()
            if r["seller_id"] == seller_id and not r.get("soft_deleted")
        ]

    def save(self, record: dict[str, Any]) -> None:
        key_id: uuid.UUID = record["id"]
        self.rows[key_id] = dict(record)
        self.by_fp[(record["platform"], record["fingerprint"])] = key_id

    def list_routable(self) -> list[dict[str, Any]]:
        from app.domain.sellerkeys.lifecycle import has_positive_quota, routable

        return [
            dict(r)
            for r in self.rows.values()
            if routable(str(r.get("administrative_state")), str(r.get("health_state")))
            and has_positive_quota(r.get("remaining_quota"))
            and r.get("ciphertext")
            and not r.get("soft_deleted")
        ]

    def apply_health(self, key_id: uuid.UUID, health: str) -> None:
        row = self.rows.get(key_id)
        if row is None:
            return
        row["health_state"] = health
