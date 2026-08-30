"""Async SMS delivery finalization — OTP PRF recompute, no automatic resend."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings
from app.domain.authentication.models import VerificationChallenge
from app.observability import (
    emit_auth_event,
    record_auth_provider_outcome,
    redact_message,
)
from app.repositories.authentication import AuthenticationRepository, utc_now
from app.security.otp import derive_otp
from app.sms.port import (
    SmsDeliveryPort,
    SmsDeliveryRequest,
    SmsDeliveryResult,
    SmsDeliveryStatus,
)

logger = logging.getLogger("api-service")

TEMPLATE = "login_verification_v1"


@dataclass(frozen=True)
class DeliveryWorkItem:
    challenge_id: uuid.UUID
    provider_request_ref: uuid.UUID
    user_id: uuid.UUID | None
    phone_ref: bytes
    code_key_version: int | None
    expires_at: datetime
    created_at: datetime
    is_decoy: bool


@dataclass
class DeliveryOutcome:
    challenge_id: uuid.UUID
    state: Literal["delivered", "delivery_failed"]
    provider_outcome: str
    sent: bool


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DeliveryService:
    """Process one claimed challenge: recheck user, send once, finalize."""

    def __init__(
        self,
        session: AsyncSession,
        settings: AuthSettings,
        sms: SmsDeliveryPort,
    ) -> None:
        self._session = session
        self._settings = settings
        self._sms = sms
        self._repo = AuthenticationRepository(session)

    async def prepare_and_send(
        self,
        challenge: VerificationChallenge,
        *,
        owner: str,
        request_id: str,
        destination_phone: str | None,
    ) -> DeliveryOutcome:
        """Mark send-started (if eligible), call port at most once, finalize.

        Caller must not hold a DB transaction open during the provider I/O.
        This method uses short transactions around state transitions.
        """
        now = utc_now()
        challenge_id = challenge.id

        # Decoy: no user and no registration phone. Registration challenges
        # (phone_normalized set) are delivered through the provider path.
        if challenge.user_id is None and not challenge.phone_normalized:
            locked = await self._repo.lock_challenge(challenge_id)
            if locked is None or locked.state != "pending_delivery":
                return DeliveryOutcome(
                    challenge_id=challenge_id,
                    state="delivery_failed",
                    provider_outcome="skipped_state",
                    sent=False,
                )
            await self._repo.finalize_delivered(locked, now=now)
            await self._repo.append_security_event(
                event_type="challenge_requested",
                outcome="success",
                reason_code="decoy_delivered",
                request_id=request_id,
                challenge_id=challenge_id,
                subject_ref=locked.phone_ref,
                now=now,
            )
            await self._repo.commit()
            record_auth_provider_outcome("decoy_delivered")
            emit_auth_event(
                logger,
                "auth.provider.outcome",
                request_id=request_id,
                outcome="decoy_delivered",
            )
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivered",
                provider_outcome="decoy_delivered",
                sent=False,
            )

        # Eligible login or registration-delivery path.
        user = None
        if challenge.user_id is not None:
            user = await self._repo.lock_user_by_id(challenge.user_id)
        locked = await self._repo.lock_challenge(challenge_id)
        if locked is None:
            await self._repo.rollback()
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="missing",
                sent=False,
            )

        if challenge.user_id is not None and not self._repo.is_auth_eligible(user):
            await self._repo.finalize_delivery_failed(locked, clear_otp=True, now=now)
            await self._repo.append_security_event(
                event_type="delivery_failed",
                outcome="failed",
                reason_code="user_ineligible",
                request_id=request_id,
                user_id=challenge.user_id,
                challenge_id=challenge_id,
                now=now,
            )
            await self._repo.commit()
            record_auth_provider_outcome("user_ineligible")
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="user_ineligible",
                sent=False,
            )

        # Phone identity: user row is source of destination; phone_ref must still match
        # the normalized phone HMAC (recomputed by dispatcher from user phone).
        if destination_phone is None:
            await self._repo.finalize_delivery_failed(locked, clear_otp=True, now=now)
            await self._repo.commit()
            record_auth_provider_outcome("missing_destination")
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="missing_destination",
                sent=False,
            )

        marked = await self._repo.mark_send_started(locked, owner=owner, now=now)
        if not marked:
            await self._repo.rollback()
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="lease_lost",
                sent=False,
            )
        provider_ref = locked.provider_request_ref
        key_version = locked.code_key_version
        expires_at = _ensure_aware(locked.expires_at)
        await self._repo.commit()

        # Outside transaction: recompute OTP via PRF and call provider once.
        otp_mat = self._settings.key_material("otp")
        key = otp_mat.resolve(int(key_version or otp_mat.version))
        if key is None:
            await self._fail_after_send_started(
                challenge_id, request_id=request_id, outcome="configuration_invalid"
            )
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="configuration_invalid",
                sent=False,
            )

        code = derive_otp(key, challenge_id)
        sms_request = SmsDeliveryRequest(
            provider_request_ref=provider_ref,
            destination=destination_phone,
            code=code,
            expires_at=expires_at,
            template=TEMPLATE,
            request_id=request_id,
        )
        # Scrub local plaintext ASAP after building request (still needed for send).
        try:
            result = await self._sms.send(sms_request)
        except TimeoutError:
            result = SmsDeliveryResult.unavailable(
                category=__import__(
                    "app.sms.port", fromlist=["DeliveryCategory"]
                ).DeliveryCategory.provider_timeout
            )
        except Exception as exc:  # noqa: BLE001 — map to unknown; never log body
            logger.warning(
                redact_message(
                    f"sms adapter error request_id={request_id} "
                    f"err_type={type(exc).__name__}"
                )
            )
            result = SmsDeliveryResult.unknown_result()
        finally:
            del code
            del sms_request

        return await self.finalize_result(
            challenge_id,
            result=result,
            request_id=request_id,
            user_id=challenge.user_id,
        )

    async def finalize_result(
        self,
        challenge_id: uuid.UUID,
        *,
        result: SmsDeliveryResult,
        request_id: str,
        user_id: uuid.UUID | None = None,
    ) -> DeliveryOutcome:
        now = utc_now()
        locked = await self._repo.lock_challenge(challenge_id)
        if locked is None:
            await self._repo.rollback()
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="missing",
                sent=True,
            )
        if locked.state not in ("dispatching", "pending_delivery"):
            await self._repo.rollback()
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state=(
                    "delivery_failed"
                    if locked.state == "delivery_failed"
                    else "delivered"
                ),
                provider_outcome="already_final",
                sent=True,
            )

        outcome_label = result.status.value
        if result.status is SmsDeliveryStatus.accepted:
            await self._repo.finalize_delivered(locked, now=now)
            await self._repo.append_security_event(
                event_type="challenge_requested",
                outcome="success",
                reason_code="delivery_accepted",
                request_id=request_id,
                user_id=user_id,
                challenge_id=challenge_id,
                now=now,
            )
            final_state: Literal["delivered", "delivery_failed"] = "delivered"
        else:
            await self._repo.finalize_delivery_failed(locked, clear_otp=True, now=now)
            await self._repo.append_security_event(
                event_type="delivery_failed",
                outcome="failed",
                reason_code=outcome_label[:64],
                request_id=request_id,
                user_id=user_id,
                challenge_id=challenge_id,
                safe_metadata={
                    "category": result.category.value if result.category else "unknown"
                },
                now=now,
            )
            final_state = "delivery_failed"

        await self._repo.commit()
        record_auth_provider_outcome(outcome_label)
        emit_auth_event(
            logger,
            "auth.provider.outcome",
            request_id=request_id,
            outcome=outcome_label,
        )
        emit_auth_event(
            logger,
            "auth.dispatcher.finalize",
            request_id=request_id,
            state=final_state,
        )
        return DeliveryOutcome(
            challenge_id=challenge_id,
            state=final_state,
            provider_outcome=outcome_label,
            sent=True,
        )

    async def invalidate_after_send_started(
        self,
        challenge_id: uuid.UUID,
        *,
        request_id: str,
        reason: str = "unknown_after_restart",
    ) -> DeliveryOutcome:
        """Post-send_started recovery: never resend; query or invalidate."""
        ch = await self._repo.get_challenge(challenge_id)
        if ch is None:
            return DeliveryOutcome(
                challenge_id=challenge_id,
                state="delivery_failed",
                provider_outcome="missing",
                sent=False,
            )
        query = await self._sms.query_status(ch.provider_request_ref)
        if query is not None and query.status is SmsDeliveryStatus.accepted:
            return await self.finalize_result(
                challenge_id,
                result=query,
                request_id=request_id,
                user_id=ch.user_id,
            )
        now = utc_now()
        locked = await self._repo.lock_challenge(challenge_id)
        if locked and locked.state == "dispatching":
            await self._repo.finalize_delivery_failed(locked, clear_otp=True, now=now)
            await self._repo.append_security_event(
                event_type="delivery_failed",
                outcome="failed",
                reason_code=reason[:64],
                request_id=request_id,
                challenge_id=challenge_id,
                now=now,
            )
            await self._repo.commit()
            record_auth_provider_outcome(reason)
        return DeliveryOutcome(
            challenge_id=challenge_id,
            state="delivery_failed",
            provider_outcome=reason,
            sent=False,
        )

    async def _fail_after_send_started(
        self,
        challenge_id: uuid.UUID,
        *,
        request_id: str,
        outcome: str,
    ) -> None:
        now = utc_now()
        locked = await self._repo.lock_challenge(challenge_id)
        if locked is None:
            return
        await self._repo.finalize_delivery_failed(locked, clear_otp=True, now=now)
        await self._repo.append_security_event(
            event_type="delivery_failed",
            outcome="failed",
            reason_code=outcome[:64],
            request_id=request_id,
            challenge_id=challenge_id,
            now=now,
        )
        await self._repo.commit()
        record_auth_provider_outcome(outcome)
