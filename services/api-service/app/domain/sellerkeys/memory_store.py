"""In-memory KeyStore for unit tests."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from app.domain.owners import OwnerState, owner_state_allows_seller


class MemoryKeyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_fp: dict[tuple[str, str], uuid.UUID] = {}
        self.rows: dict[uuid.UUID, dict[str, Any]] = {}
        self.idem: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID | None]] = {}
        self.owners: dict[uuid.UUID, OwnerState] = {}

    def set_owner(
        self,
        user_id: uuid.UUID,
        *,
        status: str,
        role: str,
        is_deleted: bool = False,
    ) -> None:
        with self._lock:
            self.owners[user_id] = OwnerState(
                status=status, role=role, is_deleted=is_deleted
            )

    def find_by_fingerprint(self, platform: str, fingerprint: str) -> uuid.UUID | None:
        with self._lock:
            return self.by_fp.get((platform, fingerprint))

    def insert(self, record: dict[str, Any]) -> uuid.UUID:
        key_id: uuid.UUID = record["id"]
        with self._lock:
            if (record["platform"], record["fingerprint"]) in self.by_fp:
                raise ValueError("duplicate")
            self.by_fp[(record["platform"], record["fingerprint"])] = key_id
            self.rows[key_id] = dict(record)
            seller_id = record["seller_id"]
            if seller_id not in self.owners:
                self.owners[seller_id] = OwnerState(
                    status="active", role="seller", is_deleted=False
                )
        return key_id

    def get_idempotency(
        self, actor_id: uuid.UUID, key: str
    ) -> tuple[str, uuid.UUID | None] | None:
        with self._lock:
            return self.idem.get((actor_id, key))

    def put_idempotency(
        self,
        key: str,
        seller_id: uuid.UUID,
        digest: str,
        code: str,
        key_id: uuid.UUID | None,
    ) -> None:
        with self._lock:
            self.idem[(seller_id, key)] = (digest, key_id)

    def get(self, key_id: uuid.UUID) -> dict[str, Any] | None:
        with self._lock:
            row = self.rows.get(key_id)
            return dict(row) if row is not None else None

    def list_by_seller(self, seller_id: uuid.UUID) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(r)
                for r in self.rows.values()
                if r["seller_id"] == seller_id and not r.get("soft_deleted")
            ]

    def save(self, record: dict[str, Any]) -> None:
        key_id: uuid.UUID = record["id"]
        with self._lock:
            self.rows[key_id] = dict(record)
            self.by_fp[(record["platform"], record["fingerprint"])] = key_id

    def save_if_unmodified(self, record: dict[str, Any], expected_version: int) -> bool:
        key_id: uuid.UUID = record["id"]
        with self._lock:
            existing = self.rows.get(key_id)
            if existing is None:
                return False
            if int(existing.get("version") or 0) != expected_version:
                return False
            if str(existing.get("administrative_state")) == "revoked":
                return False
            self.rows[key_id] = dict(record)
            self.by_fp[(record["platform"], record["fingerprint"])] = key_id
            return True

    def persisted_key_versions(self) -> set[str]:
        with self._lock:
            return {
                str(r.get("key_version"))
                for r in self.rows.values()
                if r.get("key_version") and not r.get("soft_deleted")
            }

    def list_routable(self) -> list[dict[str, Any]]:
        from app.domain.sellerkeys.lifecycle import has_positive_quota, routable

        with self._lock:
            out: list[dict[str, Any]] = []
            for r in self.rows.values():
                if not (
                    routable(
                        str(r.get("administrative_state")), str(r.get("health_state"))
                    )
                    and has_positive_quota(r.get("remaining_quota"))
                    and r.get("ciphertext")
                    and not r.get("soft_deleted")
                ):
                    continue
                owner = self.owners.get(r["seller_id"])
                if not owner_state_allows_seller(owner):
                    continue
                out.append(dict(r))
            return out

    def apply_health(self, key_id: uuid.UUID, health: str) -> None:
        with self._lock:
            row = self.rows.get(key_id)
            if row is None:
                return
            row["health_state"] = health
