"""Onboarding use-case: validate then encrypt-and-persist."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.domain.sellerkeys.codes import (
    CODE_DUPLICATE,
    CODE_ENCRYPTION,
    CODE_FORBIDDEN,
    CODE_INVALID_KEY,
    CODE_RATE_LIMITED,
    CODE_TEMPORARY,
    CODE_UNAUTHORIZED,
    CODE_UNSUPPORTED_PLATFORM,
    CODE_ZERO_QUOTA,
    MSG,
    OnboardingError,
)
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.fingerprint import fingerprint_key, normalize_key
from app.domain.sellerkeys.validator_port import CredentialValidator, ValidationSnapshot


def mask_hint(api_key: str) -> str:
    k = normalize_key(api_key)
    if len(k) <= 8:
        return "****"
    return k[:3] + "****" + k[-4:]


def request_digest(platform: str, api_key: str) -> str:
    return hashlib.sha256(f"{platform}|{normalize_key(api_key)}".encode()).hexdigest()


@dataclass
class OnboardResult:
    key_id: uuid.UUID
    platform: str
    masked_hint: str
    remaining_quota: str | None
    quota_unit: str | None
    administrative_state: str
    health_state: str
    last_validated_at: datetime
    replayed: bool = False


class KeyStore(Protocol):
    def find_by_fingerprint(
        self, platform: str, fingerprint: str
    ) -> uuid.UUID | None: ...

    def insert(self, record: dict[str, Any]) -> uuid.UUID: ...

    def get_idempotency(self, key: str) -> tuple[str, uuid.UUID | None] | None: ...

    def put_idempotency(
        self,
        key: str,
        seller_id: uuid.UUID,
        digest: str,
        code: str,
        key_id: uuid.UUID | None,
    ) -> None: ...

    def get(self, key_id: uuid.UUID) -> dict[str, Any] | None: ...

    def list_by_seller(self, seller_id: uuid.UUID) -> list[dict[str, Any]]: ...

    def save(self, record: dict[str, Any]) -> None: ...

    def list_routable(self) -> list[dict[str, Any]]: ...

    def apply_health(self, key_id: uuid.UUID, health: str) -> None: ...


_REJECT = {
    "invalid": (CODE_INVALID_KEY, 400),
    "forbidden": (CODE_FORBIDDEN, 403),
    "zero_quota": (CODE_ZERO_QUOTA, 402),
    "rate_limited": (CODE_RATE_LIMITED, 429),
    "temporary_unavailable": (CODE_TEMPORARY, 503),
    "timeout": (CODE_TEMPORARY, 503),
    "invalid_response": (CODE_TEMPORARY, 503),
    "unsupported_platform": (CODE_UNSUPPORTED_PLATFORM, 400),
}


class OnboardingService:
    def __init__(
        self,
        *,
        validator: CredentialValidator,
        encryptor: CredentialEncryptor,
        store: KeyStore,
        fingerprint_secret: bytes,
    ) -> None:
        self._validator = validator
        self._encryptor = encryptor
        self._store = store
        self._fp_secret = fingerprint_secret

    def onboard(
        self,
        *,
        seller_id: uuid.UUID,
        role: str,
        platform: str,
        api_key: str,
        idempotency_key: str,
        request_id: str,
    ) -> OnboardResult:
        if role not in ("seller", "both"):
            raise OnboardingError(
                CODE_UNAUTHORIZED, MSG[CODE_UNAUTHORIZED], http_status=403
            )
        if platform != "volcano":
            raise OnboardingError(
                CODE_UNSUPPORTED_PLATFORM,
                MSG[CODE_UNSUPPORTED_PLATFORM],
                http_status=400,
            )
        api_key = normalize_key(api_key)
        digest = request_digest(platform, api_key)
        existing = self._store.get_idempotency(idempotency_key)
        if existing:
            prev_digest, prev_id = existing
            if prev_digest != digest:
                raise OnboardingError(
                    "IDEMPOTENCY_CONFLICT", "幂等键与请求内容不一致", http_status=409
                )
            if prev_id is None:
                raise OnboardingError(
                    CODE_TEMPORARY, MSG[CODE_TEMPORARY], http_status=503
                )
            now = datetime.now(timezone.utc)
            return OnboardResult(
                key_id=prev_id,
                platform=platform,
                masked_hint="********",
                remaining_quota=None,
                quota_unit=None,
                administrative_state="active",
                health_state="unknown",
                last_validated_at=now,
                replayed=True,
            )

        snap: ValidationSnapshot = self._validator.validate(
            platform=platform, api_key=api_key, request_id=request_id
        )
        cat = snap.error_category
        if cat in _REJECT:
            code, status = _REJECT[cat]
            raise OnboardingError(code, MSG[code], http_status=status)

        # success+quota>0, or SF06 quota_unavailable after valid auth
        if cat not in ("success", "quota_unavailable"):
            raise OnboardingError(CODE_TEMPORARY, MSG[CODE_TEMPORARY], http_status=503)
        if cat == "success":
            if not snap.remaining_quota or snap.remaining_quota in ("0", "0.0"):
                raise OnboardingError(
                    CODE_ZERO_QUOTA, MSG[CODE_ZERO_QUOTA], http_status=402
                )
            health = "healthy"
        else:
            health = "unknown"

        fp = fingerprint_key(api_key, self._fp_secret, platform=platform)
        dup = self._store.find_by_fingerprint(platform, fp)
        if dup is not None:
            raise OnboardingError(CODE_DUPLICATE, MSG[CODE_DUPLICATE], http_status=409)

        try:
            nonce, ct, tag = self._encryptor.encrypt(api_key.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise OnboardingError(
                CODE_ENCRYPTION, MSG[CODE_ENCRYPTION], http_status=503
            ) from exc

        now = datetime.now(timezone.utc)
        key_id = uuid.uuid4()
        record = {
            "id": key_id,
            "seller_id": seller_id,
            "platform": platform,
            "fingerprint": fp,
            "masked_hint": mask_hint(api_key),
            "ciphertext": ct,
            "nonce": nonce,
            "tag": tag,
            "key_version": self._encryptor.key_version,
            "remaining_quota": snap.remaining_quota,
            "quota_unit": snap.quota_unit,
            "administrative_state": "active",
            "health_state": health,
            "last_validated_at": now,
            "created_request_id": request_id,
        }
        try:
            stored = self._store.insert(record)
        except ValueError as exc:
            if str(exc) == "duplicate":
                raise OnboardingError(
                    CODE_DUPLICATE, MSG[CODE_DUPLICATE], http_status=409
                ) from exc
            raise
        self._store.put_idempotency(idempotency_key, seller_id, digest, "0", stored)
        return OnboardResult(
            key_id=stored,
            platform=platform,
            masked_hint=mask_hint(api_key),
            remaining_quota=snap.remaining_quota,
            quota_unit=snap.quota_unit,
            administrative_state="active",
            health_state=health,
            last_validated_at=now,
        )
