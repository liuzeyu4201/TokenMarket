"""Administrative state machine and lifecycle use-case (SF09)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.domain.sellerkeys.codes import (
    CODE_CONFLICT,
    CODE_NOT_FOUND,
    CODE_UNAUTHORIZED,
    CODE_VALIDATION_FAILED,
    CODE_ZERO_QUOTA,
    MSG,
    OnboardingError,
)
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.service import KeyStore
from app.domain.sellerkeys.validator_port import CredentialValidator

ALLOWED = {
    ("active", "paused"),
    ("paused", "active"),
    ("active", "revoked"),
    ("paused", "revoked"),
}


def transition(current: str, target: str) -> str:
    if current == target == "revoked":
        return "revoked"
    if current == "revoked":
        raise OnboardingError(CODE_CONFLICT, MSG[CODE_CONFLICT], http_status=409)
    if (current, target) not in ALLOWED:
        raise OnboardingError(CODE_CONFLICT, MSG[CODE_CONFLICT], http_status=409)
    return target


def routable(administrative_state: str, health_state: str) -> bool:
    return administrative_state == "active" and health_state == "healthy"


class LifecycleService:
    def __init__(
        self,
        *,
        store: KeyStore,
        encryptor: CredentialEncryptor,
        validator: CredentialValidator,
    ) -> None:
        self._store = store
        self._encryptor = encryptor
        self._validator = validator

    def _owned(self, key_id: uuid.UUID, seller_id: uuid.UUID) -> dict[str, Any]:
        row = self._store.get(key_id)
        if row is None or row.get("seller_id") != seller_id:
            raise OnboardingError(CODE_NOT_FOUND, MSG[CODE_NOT_FOUND], http_status=404)
        return row

    def get(self, key_id: uuid.UUID, seller_id: uuid.UUID, role: str) -> dict[str, Any]:
        self._require_seller(role)
        return _public_view(self._owned(key_id, seller_id))

    def list(self, seller_id: uuid.UUID, role: str) -> list[dict[str, Any]]:
        self._require_seller(role)
        return [_public_view(r) for r in self._store.list_by_seller(seller_id)]

    def pause(
        self, key_id: uuid.UUID, seller_id: uuid.UUID, role: str
    ) -> dict[str, Any]:
        self._require_seller(role)
        row = self._owned(key_id, seller_id)
        row["administrative_state"] = transition(
            str(row["administrative_state"]), "paused"
        )
        row["version"] = int(row.get("version") or 1) + 1
        row["updated_at"] = datetime.now(timezone.utc)
        self._store.save(row)
        return _public_view(row)

    def resume(
        self, key_id: uuid.UUID, seller_id: uuid.UUID, role: str, request_id: str
    ) -> dict[str, Any]:
        self._require_seller(role)
        row = self._owned(key_id, seller_id)
        if row.get("administrative_state") == "active":
            return _public_view(row)
        ct, nonce, tag = row.get("ciphertext"), row.get("nonce"), row.get("tag")
        if not ct or not nonce or not tag:
            raise OnboardingError(CODE_NOT_FOUND, MSG[CODE_NOT_FOUND], http_status=404)
        plaintext = self._encryptor.decrypt(nonce, ct, tag).decode("utf-8")
        snap = self._validator.validate(
            platform=str(row["platform"]), api_key=plaintext, request_id=request_id
        )
        if (
            snap.error_category != "success"
            or not snap.remaining_quota
            or snap.remaining_quota
            in (
                "0",
                "0.0",
            )
        ):
            if snap.error_category in ("zero_quota", "success"):
                raise OnboardingError(
                    CODE_ZERO_QUOTA, MSG[CODE_ZERO_QUOTA], http_status=402
                )
            raise OnboardingError(
                CODE_VALIDATION_FAILED, MSG[CODE_VALIDATION_FAILED], http_status=409
            )
        row["administrative_state"] = transition(
            str(row["administrative_state"]), "active"
        )
        row["health_state"] = "healthy"
        row["remaining_quota"] = snap.remaining_quota
        row["quota_unit"] = snap.quota_unit
        row["last_validated_at"] = datetime.now(timezone.utc)
        row["version"] = int(row.get("version") or 1) + 1
        row["updated_at"] = datetime.now(timezone.utc)
        self._store.save(row)
        return _public_view(row)

    def revoke(
        self, key_id: uuid.UUID, seller_id: uuid.UUID, role: str
    ) -> dict[str, Any]:
        self._require_seller(role)
        row = self._owned(key_id, seller_id)
        row["administrative_state"] = transition(
            str(row["administrative_state"]), "revoked"
        )
        row["ciphertext"] = None
        row["nonce"] = None
        row["tag"] = None
        row["version"] = int(row.get("version") or 1) + 1
        row["updated_at"] = datetime.now(timezone.utc)
        self._store.save(row)
        return _public_view(row)

    @staticmethod
    def _require_seller(role: str) -> None:
        if role not in ("seller", "both"):
            raise OnboardingError(
                CODE_UNAUTHORIZED, MSG[CODE_UNAUTHORIZED], http_status=403
            )


def _public_view(row: dict[str, Any]) -> dict[str, Any]:
    last = row.get("last_validated_at")
    last_out: Any
    if isinstance(last, datetime):
        last_out = last.isoformat()
    else:
        last_out = last
    return {
        "key_id": str(row["id"]),
        "platform": row.get("platform"),
        "masked_hint": row.get("masked_hint"),
        "remaining_quota": row.get("remaining_quota"),
        "quota_unit": row.get("quota_unit"),
        "administrative_state": row.get("administrative_state"),
        "health_state": row.get("health_state"),
        "last_validated_at": last_out,
        "version": row.get("version"),
    }
