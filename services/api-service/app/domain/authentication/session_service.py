"""OTP verification, session bootstrap, and exact-session logout."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings
from app.domain.users.privacy import mask_phone
from app.errors import (
    MSG_CHALLENGE_EXPIRED,
    MSG_CHALLENGE_UNAVAILABLE,
    MSG_CSRF_INVALID,
    MSG_PROFILE_COMPLETION_REQUIRED,
    MSG_SERVICE_UNAVAILABLE,
    MSG_UNAUTHENTICATED,
    MSG_VALIDATION,
    MSG_VERIFICATION_FAILED,
)
from app.observability import (
    emit_auth_event,
    record_auth_session_check,
    record_auth_session_event,
    record_auth_session_rejected,
    record_auth_verify,
)
from app.repositories.authentication import (
    MAX_ATTEMPTS,
    AuthenticationRepository,
    utc_now,
)
from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.otp import verify_otp_digest
from app.security.session import (
    generate_session_token,
    parse_session_cookie,
    token_digest,
)

logger = logging.getLogger("api-service")


@dataclass
class SessionIssueResult:
    kind: Literal[
        "success",
        "profile_completion",
        "validation",
        "verification_failed",
        "challenge_unavailable",
        "challenge_expired",
        "service_unavailable",
    ]
    http_status: int
    code: str
    message: str
    data: Any = None
    # Only set on success — apply to response after commit.
    cookie_value: str | None = None
    profile_cookie_value: str | None = None


@dataclass
class SessionBootstrapResult:
    kind: Literal["success", "unauthenticated", "service_unavailable"]
    http_status: int
    code: str
    message: str
    data: Any = None
    clear_cookie: bool = False
    reject_reason: str | None = None


@dataclass
class SessionLogoutResult:
    kind: Literal["success", "csrf_invalid", "service_unavailable"]
    http_status: int
    code: str
    message: str
    data: Any = None
    clear_cookie: bool = False


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_six_digit_ascii(code: str) -> bool:
    return (
        isinstance(code, str) and len(code) == 6 and code.isascii() and code.isdigit()
    )


class SessionService:
    """Verify challenge, issue/bootstrap session, and exact-session logout."""

    def __init__(self, session: AsyncSession, settings: AuthSettings) -> None:
        self._session = session
        self._settings = settings
        self._repo = AuthenticationRepository(session)

    def _session_summary(
        self,
        *,
        user_id: uuid.UUID,
        nickname: str,
        phone_normalized: str,
        role: Any,
        expires_at: datetime,
        csrf_token: str,
    ) -> dict[str, Any]:
        role_value = role.value if hasattr(role, "value") else str(role)
        return {
            "user_id": str(user_id),
            "nickname": nickname,
            "phone_masked": mask_phone(phone_normalized),
            "role": role_value,
            "expires_at": _ensure_aware(expires_at),
            "csrf_token": csrf_token,
        }

    async def bootstrap_session(
        self,
        *,
        cookie_value: str | None,
        request_id: str,
    ) -> SessionBootstrapResult:
        """Validate cookie session + account state; return summary or clear cookie."""
        start = time.monotonic()
        try:
            return await self._bootstrap_session_inner(
                cookie_value=cookie_value, request_id=request_id
            )
        except (OperationalError, SQLAlchemyError):
            logger.exception(
                "session bootstrap dependency failure",
                extra={"request_id": request_id},
            )
            record_auth_session_check(time.monotonic() - start)
            record_auth_session_event("bootstrap_unavailable")
            emit_auth_event(
                logger,
                "auth.session.rejected",
                request_id=request_id,
                reason="dependency",
            )
            return SessionBootstrapResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
                reject_reason="dependency",
            )

    async def _bootstrap_session_inner(
        self,
        *,
        cookie_value: str | None,
        request_id: str,
    ) -> SessionBootstrapResult:
        start = time.monotonic()
        session_mat = self._settings.key_material("session")
        csrf_mat = self._settings.key_material("csrf")

        if not session_mat.current_usable() or not csrf_mat.current_usable():
            record_auth_session_check(time.monotonic() - start)
            record_auth_session_event("bootstrap_unavailable")
            return SessionBootstrapResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
                reject_reason="key_unavailable",
            )

        parsed = parse_session_cookie(cookie_value)
        if parsed is None:
            record_auth_session_check(time.monotonic() - start)
            if cookie_value:
                record_auth_session_rejected("malformed")
                record_auth_session_event("bootstrap_rejected")
                emit_auth_event(
                    logger,
                    "auth.session.rejected",
                    request_id=request_id,
                    reason="malformed",
                )
                return SessionBootstrapResult(
                    kind="unauthenticated",
                    http_status=401,
                    code="UNAUTHENTICATED",
                    message=MSG_UNAUTHENTICATED,
                    clear_cookie=True,
                    reject_reason="malformed",
                )
            # No cookie: quiet anonymous — no reject metric noise.
            record_auth_session_event("bootstrap_anonymous")
            return SessionBootstrapResult(
                kind="unauthenticated",
                http_status=401,
                code="UNAUTHENTICATED",
                message=MSG_UNAUTHENTICATED,
                clear_cookie=False,
                reject_reason="missing",
            )

        key_version, opaque = parsed
        session_key = session_mat.resolve(key_version)
        if session_key is None:
            # Unknown key version: fail closed (cannot validate).
            record_auth_session_check(time.monotonic() - start)
            record_auth_session_event("bootstrap_unavailable")
            record_auth_session_rejected("unknown_key_version")
            emit_auth_event(
                logger,
                "auth.session.rejected",
                request_id=request_id,
                reason="unknown_key_version",
            )
            return SessionBootstrapResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
                reject_reason="unknown_key_version",
            )

        digest = token_digest(session_key, opaque)
        row = await self._repo.get_session_with_user_by_token_digest(
            token_key_version=key_version,
            token_digest=digest,
        )
        now = utc_now()

        if row is None:
            return self._bootstrap_unauthenticated(
                start=start,
                request_id=request_id,
                reason="unknown_token",
                clear_cookie=True,
            )

        auth_session, user = row
        expires_at = _ensure_aware(auth_session.expires_at)

        if auth_session.revoked_at is not None:
            return self._bootstrap_unauthenticated(
                start=start,
                request_id=request_id,
                reason="revoked",
                clear_cookie=True,
                session_id=auth_session.id,
                user_id=user.id,
            )

        if now >= expires_at:
            return self._bootstrap_unauthenticated(
                start=start,
                request_id=request_id,
                reason="expired",
                clear_cookie=True,
                session_id=auth_session.id,
                user_id=user.id,
            )

        if not self._repo.is_auth_eligible(user):
            return self._bootstrap_unauthenticated(
                start=start,
                request_id=request_id,
                reason="account_disabled",
                clear_cookie=True,
                session_id=auth_session.id,
                user_id=user.id,
            )

        csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, auth_session.id)
        data = self._session_summary(
            user_id=user.id,
            nickname=user.nickname,
            phone_normalized=user.phone_normalized,
            role=user.role,
            expires_at=expires_at,
            csrf_token=csrf,
        )
        duration = time.monotonic() - start
        record_auth_session_check(duration)
        record_auth_session_event("bootstrap")
        emit_auth_event(logger, "auth.session.bootstrap", request_id=request_id)
        return SessionBootstrapResult(
            kind="success",
            http_status=200,
            code="0",
            message="success",
            data=data,
            clear_cookie=False,
        )

    def _bootstrap_unauthenticated(
        self,
        *,
        start: float,
        request_id: str,
        reason: str,
        clear_cookie: bool,
        session_id: uuid.UUID | None = None,  # noqa: ARG002 — audit correlation hook
        user_id: uuid.UUID | None = None,  # noqa: ARG002 — audit correlation hook
    ) -> SessionBootstrapResult:
        record_auth_session_check(time.monotonic() - start)
        record_auth_session_rejected(reason)
        record_auth_session_event("bootstrap_rejected")
        emit_auth_event(
            logger,
            "auth.session.rejected",
            request_id=request_id,
            reason=reason,
        )
        # Best-effort audit; caller may not have a writable path for DB errors.
        return SessionBootstrapResult(
            kind="unauthenticated",
            http_status=401,
            code="UNAUTHENTICATED",
            message=MSG_UNAUTHENTICATED,
            clear_cookie=clear_cookie,
            reject_reason=reason,
        )

    async def logout_session(
        self,
        *,
        cookie_value: str | None,
        csrf_presented: str | None,
        request_id: str,
    ) -> SessionLogoutResult:
        """Idempotent exact-session revoke; Origin checked by the route."""
        try:
            return await self._logout_session_inner(
                cookie_value=cookie_value,
                csrf_presented=csrf_presented,
                request_id=request_id,
            )
        except (OperationalError, SQLAlchemyError):
            logger.exception(
                "session logout dependency failure",
                extra={"request_id": request_id},
            )
            record_auth_session_event("logout_unavailable")
            return SessionLogoutResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
            )

    async def _logout_session_inner(
        self,
        *,
        cookie_value: str | None,
        csrf_presented: str | None,
        request_id: str,
    ) -> SessionLogoutResult:
        session_mat = self._settings.key_material("session")
        csrf_mat = self._settings.key_material("csrf")

        if not session_mat.current_usable() or not csrf_mat.current_usable():
            return SessionLogoutResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
            )

        parsed = parse_session_cookie(cookie_value)
        if parsed is None:
            # Missing/malformed: idempotent success + clear any junk cookie.
            record_auth_session_event("logout_idempotent")
            emit_auth_event(logger, "auth.session.revoked", request_id=request_id)
            return SessionLogoutResult(
                kind="success",
                http_status=200,
                code="0",
                message="success",
                data={"logged_out": True},
                clear_cookie=True,
            )

        key_version, opaque = parsed
        session_key = session_mat.resolve(key_version)
        if session_key is None:
            return SessionLogoutResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
            )

        digest = token_digest(session_key, opaque)
        now = utc_now()
        auth_session = await self._repo.lock_session_by_token_digest(
            token_key_version=key_version,
            token_digest=digest,
        )

        if auth_session is None:
            await self._repo.rollback()
            record_auth_session_event("logout_idempotent")
            emit_auth_event(logger, "auth.session.revoked", request_id=request_id)
            return SessionLogoutResult(
                kind="success",
                http_status=200,
                code="0",
                message="success",
                data={"logged_out": True},
                clear_cookie=True,
            )

        expires_at = _ensure_aware(auth_session.expires_at)
        already_invalid = auth_session.revoked_at is not None or now >= expires_at

        if already_invalid:
            await self._repo.rollback()
            record_auth_session_event("logout_idempotent")
            emit_auth_event(logger, "auth.session.revoked", request_id=request_id)
            return SessionLogoutResult(
                kind="success",
                http_status=200,
                code="0",
                message="success",
                data={"logged_out": True},
                clear_cookie=True,
            )

        # Valid session: CSRF is mandatory before revoke.
        csrf_ok = self._verify_csrf_for_session(
            csrf_mat=csrf_mat,
            session_id=auth_session.id,
            presented=csrf_presented,
        )
        if csrf_ok is None:
            await self._repo.rollback()
            return SessionLogoutResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
                clear_cookie=False,
            )
        if not csrf_ok:
            await self._repo.rollback()
            record_auth_session_event("logout_csrf_rejected")
            emit_auth_event(
                logger,
                "auth.csrf.rejected",
                request_id=request_id,
                reason="csrf",
            )
            return SessionLogoutResult(
                kind="csrf_invalid",
                http_status=403,
                code="CSRF_INVALID",
                message=MSG_CSRF_INVALID,
                clear_cookie=False,
            )

        newly = await self._repo.revoke_session(auth_session, reason="logout", now=now)
        await self._repo.append_security_event(
            event_type="session_revoked",
            outcome="success",
            reason_code="logout",
            request_id=request_id,
            user_id=auth_session.user_id,
            session_id=auth_session.id,
            safe_metadata={"newly_revoked": newly},
            now=now,
        )
        await self._repo.commit()

        record_auth_session_event("revoked")
        emit_auth_event(logger, "auth.session.revoked", request_id=request_id)
        return SessionLogoutResult(
            kind="success",
            http_status=200,
            code="0",
            message="success",
            data={"logged_out": True},
            clear_cookie=True,
        )

    def _verify_csrf_for_session(
        self,
        *,
        csrf_mat: Any,
        session_id: uuid.UUID,
        presented: str | None,
    ) -> bool | None:
        """Return True/False for CSRF check, or None when key version unknown (503)."""
        if not presented or not isinstance(presented, str) or "." not in presented:
            return False
        version_s, _rest = presented.split(".", 1)
        if not version_s.isdigit():
            return False
        version = int(version_s)
        key = csrf_mat.resolve(version)
        if key is None:
            # Unknown CSRF key version while session is valid → fail closed.
            return None
        return verify_csrf_token(key, version, session_id, presented)

    async def create_session(
        self,
        *,
        challenge_id: uuid.UUID,
        code: str,
        request_id: str,
    ) -> SessionIssueResult:
        if not _is_six_digit_ascii(code):
            return SessionIssueResult(
                kind="validation",
                http_status=400,
                code="VALIDATION_ERROR",
                message=MSG_VALIDATION,
                data={"errors": {"code": ["验证码须为 6 位数字"]}},
            )

        otp_mat = self._settings.key_material("otp")
        session_mat = self._settings.key_material("session")
        csrf_mat = self._settings.key_material("csrf")
        if (
            not otp_mat.current_usable()
            or not session_mat.current_usable()
            or not csrf_mat.current_usable()
        ):
            return SessionIssueResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        # Peek challenge for user_id without lock to establish lock order.
        peek = await self._repo.get_challenge(challenge_id)
        if peek is None:
            record_auth_verify("challenge_unavailable")
            return SessionIssueResult(
                kind="challenge_unavailable",
                http_status=409,
                code="CHALLENGE_UNAVAILABLE",
                message=MSG_CHALLENGE_UNAVAILABLE,
            )

        now = utc_now()

        # Fixed lock order: user (if any) → challenge.
        user = None
        if peek.user_id is not None:
            user = await self._repo.lock_user_by_id(peek.user_id)

        challenge = await self._repo.lock_challenge(challenge_id)
        if challenge is None:
            await self._repo.rollback()
            record_auth_verify("challenge_unavailable")
            return SessionIssueResult(
                kind="challenge_unavailable",
                http_status=409,
                code="CHALLENGE_UNAVAILABLE",
                message=MSG_CHALLENGE_UNAVAILABLE,
            )

        expires_at = _ensure_aware(challenge.expires_at)
        if now >= expires_at or challenge.state == "expired":
            if challenge.state not in (
                "consumed",
                "locked",
                "superseded",
                "expired",
                "delivery_failed",
            ):
                challenge.state = "expired"
                challenge.invalidated_at = now
                challenge.code_digest = None
                challenge.code_salt = None
                # CHECK ck_vc_send_started_state: only dispatching/delivered/failed
                # may keep send_started_at.
                challenge.send_started_at = None
                await self._session.flush()
                await self._repo.commit()
            else:
                await self._repo.rollback()
            record_auth_verify("challenge_expired")
            return SessionIssueResult(
                kind="challenge_expired",
                http_status=410,
                code="CHALLENGE_EXPIRED",
                message=MSG_CHALLENGE_EXPIRED,
            )

        if challenge.state in (
            "consumed",
            "locked",
            "superseded",
            "delivery_failed",
            "pending_delivery",
            "dispatching",
        ):
            await self._repo.rollback()
            record_auth_verify("challenge_unavailable")
            return SessionIssueResult(
                kind="challenge_unavailable",
                http_status=409,
                code="CHALLENGE_UNAVAILABLE",
                message=MSG_CHALLENGE_UNAVAILABLE,
            )

        if challenge.state != "delivered":
            await self._repo.rollback()
            record_auth_verify("challenge_unavailable")
            return SessionIssueResult(
                kind="challenge_unavailable",
                http_status=409,
                code="CHALLENGE_UNAVAILABLE",
                message=MSG_CHALLENGE_UNAVAILABLE,
            )

        # Resolve OTP key version stored on the challenge.
        key_version = int(challenge.code_key_version or otp_mat.version)
        otp_key = otp_mat.resolve(key_version)
        if otp_key is None or not challenge.code_digest or not challenge.code_salt:
            await self._repo.rollback()
            record_auth_verify("challenge_unavailable")
            return SessionIssueResult(
                kind="challenge_unavailable",
                http_status=409,
                code="CHALLENGE_UNAVAILABLE",
                message=MSG_CHALLENGE_UNAVAILABLE,
            )

        ok = verify_otp_digest(
            otp_key,
            challenge.id,
            challenge.code_salt,
            code,
            challenge.code_digest,
        )

        is_register = challenge.user_id is None and bool(challenge.phone_normalized)
        is_decoy = challenge.user_id is None and not challenge.phone_normalized
        eligible = (not is_decoy) and (is_register or self._repo.is_auth_eligible(user))
        success_eligible = ok and eligible and not is_decoy

        if not success_eligible:
            challenge.attempt_count = int(challenge.attempt_count) + 1
            remaining = max(0, MAX_ATTEMPTS - challenge.attempt_count)
            if challenge.attempt_count >= MAX_ATTEMPTS:
                challenge.state = "locked"
                challenge.invalidated_at = now
                challenge.code_digest = None
                challenge.code_salt = None
                challenge.send_started_at = None
                action = "request_new_code"
                remaining_out = 0
            else:
                action = "retry_code"
                remaining_out = remaining
            reason = (
                "decoy_or_ineligible"
                if (ok and (is_decoy or not eligible))
                else "wrong_code"
            )
            await self._repo.append_security_event(
                event_type="verification_failed",
                outcome="rejected",
                reason_code=reason,
                request_id=request_id,
                user_id=challenge.user_id,
                challenge_id=challenge.id,
                safe_metadata={"attempts": challenge.attempt_count},
                now=now,
            )
            await self._repo.commit()
            record_auth_verify("failed")
            emit_auth_event(
                logger,
                "auth.verify.failed",
                request_id=request_id,
                action=action,
            )
            data: dict[str, Any] = {"action": action}
            if action == "retry_code":
                data["attempts_remaining"] = remaining_out
            return SessionIssueResult(
                kind="verification_failed",
                http_status=401,
                code="VERIFICATION_FAILED",
                message=MSG_VERIFICATION_FAILED,
                data=data,
            )

        if is_register:
            from app.security.profile_token import (
                PROFILE_MAX_AGE_SECONDS,
                generate_profile_token,
                profile_token_digest,
            )

            challenge.state = "consumed"
            challenge.consumed_at = now
            challenge.code_digest = None
            challenge.code_salt = None
            challenge.send_started_at = None
            token = generate_profile_token(session_mat.version)
            digest = profile_token_digest(session_mat.current, token.opaque_secret)
            intent_id = uuid.uuid4()
            await self._repo.insert_profile_intent(
                intent_id=intent_id,
                phone_normalized=str(challenge.phone_normalized),
                challenge_id=challenge.id,
                token_digest=digest,
                token_key_version=session_mat.version,
                now=now,
            )
            await self._repo.append_security_event(
                event_type="profile_completion_issued",
                outcome="success",
                reason_code="register_otp",
                request_id=request_id,
                challenge_id=challenge.id,
                now=now,
            )
            await self._repo.commit()
            record_auth_verify("profile_completion")
            return SessionIssueResult(
                kind="profile_completion",
                http_status=200,
                code="PROFILE_COMPLETION_REQUIRED",
                message=MSG_PROFILE_COMPLETION_REQUIRED,
                data={
                    "next_step": "complete_profile",
                    "phone_masked": mask_phone(str(challenge.phone_normalized)),
                    "expires_in_seconds": PROFILE_MAX_AGE_SECONDS,
                },
                profile_cookie_value=token.cookie_value,
            )

        assert user is not None

        # Correct + eligible: consume, revoke old sessions, insert new.
        challenge.state = "consumed"
        challenge.consumed_at = now
        challenge.code_digest = None
        challenge.code_salt = None
        challenge.send_started_at = None

        revoked = await self._repo.revoke_unrevoked_sessions(
            user.id, reason="superseded", now=now
        )
        # Mark naturally expired unrevoked rows as expired_cleanup if needed —
        # revoke_unrevoked_sessions already covers all unrevoked.

        session_id = uuid.uuid4()
        token = generate_session_token(session_mat.version)
        digest = token_digest(session_mat.current, token.opaque_secret)

        try:
            auth_session = await self._repo.insert_session(
                session_id=session_id,
                user_id=user.id,
                token_digest=digest,
                token_key_version=session_mat.version,
                role_snapshot=user.role,
                created_request_id=request_id,
                now=now,
            )
        except IntegrityError:
            await self._repo.rollback()
            record_auth_verify("conflict")
            return SessionIssueResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, auth_session.id)

        await self._repo.append_security_event(
            event_type="session_issued",
            outcome="success",
            reason_code="login",
            request_id=request_id,
            user_id=user.id,
            challenge_id=challenge.id,
            session_id=auth_session.id,
            safe_metadata={"replaced": revoked > 0},
            now=now,
        )
        if revoked:
            await self._repo.append_security_event(
                event_type="session_replaced",
                outcome="success",
                reason_code="superseded",
                request_id=request_id,
                user_id=user.id,
                session_id=auth_session.id,
                now=now,
            )

        await self._repo.commit()

        record_auth_verify("success")
        record_auth_session_event("issued")
        if revoked:
            record_auth_session_event("replaced")
        emit_auth_event(logger, "auth.verify.success", request_id=request_id)
        emit_auth_event(logger, "auth.session.issued", request_id=request_id)

        phone_masked = mask_phone(user.phone_normalized)
        role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
        return SessionIssueResult(
            kind="success",
            http_status=200,
            code="0",
            message="success",
            data={
                "user_id": str(user.id),
                "nickname": user.nickname,
                "phone_masked": phone_masked,
                "role": role_value,
                "expires_at": _ensure_aware(auth_session.expires_at),
                "csrf_token": csrf,
            },
            cookie_value=token.cookie_value,
        )
