"""Verification challenge creation — 202 committed before any provider call."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_rate_limit import AuthRateLimiter
from app.config import AuthSettings
from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile
from app.domain.users.privacy import mask_phone
from app.errors import (
    MSG_CHALLENGE_ACCEPTED,
    MSG_DELIVERY_UNAVAILABLE,
    MSG_IDEMPOTENCY_CONFLICT,
    MSG_IDEMPOTENCY_EXPIRED,
    MSG_IDEMPOTENCY_REQUIRED,
    MSG_RATE_LIMITED,
    MSG_SERVICE_UNAVAILABLE,
    MSG_VALIDATION,
)
from app.observability import (
    record_auth_rate_limited,
    record_rate_limit_backend_unavailable,
)
from app.rate_limit import RateLimitBackendUnavailable
from app.repositories.authentication import (
    CHALLENGE_TTL,
    RESEND_COOLDOWN,
    AuthenticationRepository,
    utc_now,
)
from app.security.otp import (
    derive_otp,
    generate_code_salt,
    otp_verification_digest,
)
from app.security.reference import idempotency_key_digest, ip_ref, phone_ref

logger = logging.getLogger("api-service")


@dataclass
class ChallengeResult:
    kind: Literal[
        "accepted",
        "validation",
        "idempotency_required",
        "idempotency_conflict",
        "idempotency_expired",
        "delivery_unavailable",
        "service_unavailable",
        "rate_limited",
        "replay",
    ]
    http_status: int
    code: str
    message: str
    data: Any = None
    # Internal-only: never returned to client
    is_decoy: bool = False
    challenge_id: uuid.UUID | None = None
    retry_after_seconds: int | None = None


def _validate_idempotency_key(key: str | None) -> str | ChallengeResult:
    if key is None or not str(key).strip() or len(str(key).strip()) > 64:
        return ChallengeResult(
            kind="idempotency_required",
            http_status=400,
            code="IDEMPOTENCY_KEY_REQUIRED",
            message=MSG_IDEMPOTENCY_REQUIRED,
        )
    return str(key).strip()


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ChallengeService:
    """Create pending verification challenges without calling SMS providers."""

    def __init__(
        self,
        session: AsyncSession,
        settings: AuthSettings,
        *,
        provider_health_ok: bool = True,
        rate_limiter: AuthRateLimiter | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = AuthenticationRepository(session)
        self._provider_health_ok = provider_health_ok
        self._rate_limiter = rate_limiter

    async def request_challenge(
        self,
        *,
        phone: str,
        idempotency_key: str | None,
        request_id: str,
        client_ip: str = "0.0.0.0",
    ) -> ChallengeResult:
        key_or_err = _validate_idempotency_key(idempotency_key)
        if isinstance(key_or_err, ChallengeResult):
            return key_or_err
        key = key_or_err

        phone_result = normalize_cn_mobile(phone)
        if isinstance(phone_result, PhoneValidationError):
            return ChallengeResult(
                kind="validation",
                http_status=400,
                code="VALIDATION_ERROR",
                message=MSG_VALIDATION,
                data={"errors": {"phone": [phone_result.message]}},
            )
        phone_normalized = phone_result
        phone_masked = mask_phone(phone_normalized)

        ref_mat = self._settings.key_material("reference")
        otp_mat = self._settings.key_material("otp")
        if not ref_mat.current_usable() or not otp_mat.current_usable():
            return ChallengeResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        # Provider-wide health before account branching (anti-enumeration).
        if not self._provider_health_ok:
            return ChallengeResult(
                kind="delivery_unavailable",
                http_status=503,
                code="DELIVERY_UNAVAILABLE",
                message=MSG_DELIVERY_UNAVAILABLE,
            )

        p_ref = phone_ref(ref_mat.current, phone_normalized)
        i_ref = ip_ref(ref_mat.current, client_ip or "0.0.0.0")
        k_digest = idempotency_key_digest(ref_mat.current, key)
        now = utc_now()

        record, is_winner = await self._repo.try_begin_idempotency(
            key_digest=k_digest,
            key_version=ref_mat.version,
            phone_ref=p_ref,
            now=now,
        )

        if not is_winner:
            # Replays / conflicts never re-count rate-limit buckets.
            return await self._handle_idempotency_loser(
                record, phone_ref_bytes=p_ref, now=now
            )

        # New idempotency winner: atomic phone+IP rolling limit (fail closed).
        rate_err = await self._apply_rate_limit(
            record,
            phone_ref_bytes=p_ref,
            ip_ref_bytes=i_ref,
            member_id=str(record.id),
            request_id=request_id,
            now=now,
        )
        if rate_err is not None:
            return rate_err

        # Winner path: lock user (if any), supersede old challenges, insert pending.
        user = await self._repo.lock_user_by_phone(phone_normalized)
        eligible = self._repo.is_auth_eligible(user)

        # Rolling 60s cooldown: new idempotency winners inside the window reuse
        # the current challenge's public handle (no second delivery).
        current = await self._repo.lock_current_challenges_for_phone(p_ref)
        latest_list = await self._repo.lock_latest_challenges_for_phone(p_ref)
        if latest_list:
            latest = latest_list[0]
            created = _ensure_aware(latest.created_at)
            if now - created < RESEND_COOLDOWN and latest.state in (
                "pending_delivery",
                "dispatching",
                "delivered",
            ):
                payload = {
                    "challenge_id": str(latest.id),
                    "phone_masked": phone_masked,
                    "expires_at": _ensure_aware(latest.expires_at).isoformat(),
                    "resend_available_at": (created + RESEND_COOLDOWN).isoformat(),
                }
                await self._repo.complete_idempotency(
                    record,
                    http_status=202,
                    result_code="0",
                    result_payload=payload,
                    state="succeeded",
                    now=now,
                )
                await self._repo.append_security_event(
                    event_type="challenge_requested",
                    outcome="success",
                    reason_code="cooldown_reuse",
                    request_id=request_id,
                    user_id=user.id if eligible and user else None,
                    challenge_id=latest.id,
                    subject_ref=p_ref,
                    safe_metadata={"cooldown": True},
                    now=now,
                )
                await self._repo.commit()
                return ChallengeResult(
                    kind="accepted",
                    http_status=202,
                    code="0",
                    message=MSG_CHALLENGE_ACCEPTED,
                    data={
                        "challenge_id": str(latest.id),
                        "phone_masked": phone_masked,
                        "expires_at": _ensure_aware(latest.expires_at),
                        "resend_available_at": created + RESEND_COOLDOWN,
                    },
                    is_decoy=latest.user_id is None,
                    challenge_id=latest.id,
                )

        if current:
            await self._repo.supersede_challenges(current, now=now)
        for ch in latest_list:
            if ch.state == "dispatching":
                await self._repo.supersede_challenges([ch], now=now)

        challenge_id = uuid.uuid4()
        provider_request_ref = uuid.uuid4()
        # Derive OTP in memory; persist only verification digest + salt.
        code = derive_otp(otp_mat.current, challenge_id)
        salt = generate_code_salt()
        digest = otp_verification_digest(otp_mat.current, challenge_id, salt, code)
        # Drop plaintext immediately from locals after digest (keep for clarity
        # that we never flush it — code is not assigned to any model field).
        del code

        user_id = user.id if eligible and user is not None else None
        challenge = await self._repo.insert_pending_challenge(
            challenge_id=challenge_id,
            user_id=user_id,
            idempotency_record_id=record.id,
            phone_ref=p_ref,
            code_digest=digest,
            code_salt=salt,
            code_key_version=otp_mat.version,
            provider_request_ref=provider_request_ref,
            now=now,
        )

        expires_at = _ensure_aware(challenge.expires_at)
        resend_at = now + RESEND_COOLDOWN
        payload = {
            "challenge_id": str(challenge.id),
            "phone_masked": phone_masked,
            "expires_at": expires_at.isoformat(),
            "resend_available_at": resend_at.isoformat(),
        }
        await self._repo.complete_idempotency(
            record,
            http_status=202,
            result_code="0",
            result_payload=payload,
            state="succeeded",
            now=now,
        )
        await self._repo.append_security_event(
            event_type="challenge_requested",
            outcome="success",
            reason_code="accepted" if eligible else "decoy",
            request_id=request_id,
            user_id=user_id,
            challenge_id=challenge.id,
            subject_ref=p_ref,
            safe_metadata={"decoy": not eligible},
            now=now,
        )
        # Commit public 202 before any dispatcher SMS send.
        await self._repo.commit()

        return ChallengeResult(
            kind="accepted",
            http_status=202,
            code="0",
            message=MSG_CHALLENGE_ACCEPTED,
            data={
                "challenge_id": str(challenge.id),
                "phone_masked": phone_masked,
                "expires_at": expires_at,
                "resend_available_at": resend_at,
            },
            is_decoy=user_id is None,
            challenge_id=challenge.id,
        )

    async def _apply_rate_limit(
        self,
        record: Any,
        *,
        phone_ref_bytes: bytes,
        ip_ref_bytes: bytes,
        member_id: str,
        request_id: str,
        now: datetime,
    ) -> ChallengeResult | None:
        """Count this winner once. Returns a terminal result on deny/backend down."""
        if self._rate_limiter is None:
            # Fail closed when auth rate limiter is not wired.
            record_rate_limit_backend_unavailable()
            await self._repo.complete_idempotency(
                record,
                http_status=503,
                result_code="SERVICE_UNAVAILABLE",
                result_payload=None,
                state="failed",
                now=now,
            )
            await self._repo.append_security_event(
                event_type="challenge_rate_limited",
                outcome="failed",
                reason_code="backend_unavailable",
                request_id=request_id,
                subject_ref=phone_ref_bytes,
                now=now,
            )
            await self._repo.commit()
            return ChallengeResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        try:
            decision = await self._rate_limiter.check_and_increment(
                phone_ref=phone_ref_bytes,
                ip_ref=ip_ref_bytes,
                member_id=member_id,
            )
        except RateLimitBackendUnavailable:
            record_rate_limit_backend_unavailable()
            await self._repo.complete_idempotency(
                record,
                http_status=503,
                result_code="SERVICE_UNAVAILABLE",
                result_payload=None,
                state="failed",
                now=now,
            )
            await self._repo.append_security_event(
                event_type="challenge_rate_limited",
                outcome="failed",
                reason_code="backend_unavailable",
                request_id=request_id,
                subject_ref=phone_ref_bytes,
                now=now,
            )
            await self._repo.commit()
            return ChallengeResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        if decision.allowed:
            return None

        retry_after = max(1, int(decision.retry_after_seconds or 1))
        record_auth_rate_limited()
        payload = {"retry_after_seconds": retry_after}
        await self._repo.complete_idempotency(
            record,
            http_status=429,
            result_code="RATE_LIMITED",
            result_payload=payload,
            state="failed",
            now=now,
        )
        await self._repo.append_security_event(
            event_type="challenge_rate_limited",
            outcome="rejected",
            reason_code="rate_limited",
            request_id=request_id,
            subject_ref=phone_ref_bytes,
            safe_metadata={"retry_after_seconds": retry_after},
            now=now,
        )
        await self._repo.commit()
        return ChallengeResult(
            kind="rate_limited",
            http_status=429,
            code="RATE_LIMITED",
            message=MSG_RATE_LIMITED,
            data=payload,
            retry_after_seconds=retry_after,
        )

    async def _handle_idempotency_loser(
        self,
        record: Any,
        *,
        phone_ref_bytes: bytes,
        now: datetime,
    ) -> ChallengeResult:
        replay_until = _ensure_aware(record.replay_until)
        if now >= replay_until:
            return ChallengeResult(
                kind="idempotency_expired",
                http_status=409,
                code="IDEMPOTENCY_KEY_EXPIRED",
                message=MSG_IDEMPOTENCY_EXPIRED,
            )
        if record.phone_ref != phone_ref_bytes:
            return ChallengeResult(
                kind="idempotency_conflict",
                http_status=409,
                code="IDEMPOTENCY_KEY_CONFLICT",
                message=MSG_IDEMPOTENCY_CONFLICT,
            )
        if record.state == "processing":
            # Concurrent winner still running — treat as unavailable briefly.
            return ChallengeResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )
        if record.state == "failed":
            code = str(record.result_code or "SERVICE_UNAVAILABLE")
            http_status = int(record.http_status or 503)
            payload = record.result_payload
            if code == "RATE_LIMITED":
                retry = 1
                if isinstance(payload, dict) and payload.get("retry_after_seconds"):
                    retry = max(1, int(payload["retry_after_seconds"]))
                return ChallengeResult(
                    kind="rate_limited",
                    http_status=429,
                    code="RATE_LIMITED",
                    message=MSG_RATE_LIMITED,
                    data={"retry_after_seconds": retry},
                    retry_after_seconds=retry,
                )
            return ChallengeResult(
                kind="replay",
                http_status=http_status,
                code=code,
                message=(
                    MSG_SERVICE_UNAVAILABLE
                    if code == "SERVICE_UNAVAILABLE"
                    else MSG_SERVICE_UNAVAILABLE
                ),
                data=payload,
            )
        # succeeded — replay payload
        payload = dict(record.result_payload or {})
        # Normalize datetime fields if stored as ISO strings.
        data = {
            "challenge_id": payload.get("challenge_id"),
            "phone_masked": payload.get("phone_masked"),
            "expires_at": payload.get("expires_at"),
            "resend_available_at": payload.get("resend_available_at"),
        }
        for field in ("expires_at", "resend_available_at"):
            val = data.get(field)
            if isinstance(val, str):
                data[field] = datetime.fromisoformat(val)
        return ChallengeResult(
            kind="replay",
            http_status=int(record.http_status or 202),
            code=str(record.result_code or "0"),
            message=(
                MSG_CHALLENGE_ACCEPTED
                if record.result_code == "0"
                else MSG_SERVICE_UNAVAILABLE
            ),
            data=data,
        )


# Silence unused import guard for CHALLENGE_TTL re-export convenience in tests.
__all__ = [
    "CHALLENGE_TTL",
    "RESEND_COOLDOWN",
    "ChallengeResult",
    "ChallengeService",
]
