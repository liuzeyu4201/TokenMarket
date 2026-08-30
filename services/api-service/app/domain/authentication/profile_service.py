"""Atomic profile completion: create user + session from OTP intent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings
from app.domain.users.privacy import mask_phone
from app.domain.users.service import RegistrationService
from app.errors import (
    MSG_AUTH_VERIFICATION_REQUIRED,
    MSG_PROFILE_EXPIRED,
    MSG_SERVICE_UNAVAILABLE,
)
from app.repositories.authentication import AuthenticationRepository, utc_now
from app.security.csrf import issue_csrf_token
from app.security.profile_token import parse_profile_cookie, profile_token_digest
from app.security.reference import client_hint
from app.security.session import generate_session_token, token_digest


@dataclass
class ProfileCompleteResult:
    kind: Literal[
        "success",
        "unauthenticated",
        "conflict",
        "service_unavailable",
        "validation",
    ]
    http_status: int
    code: str
    message: str
    data: Any = None
    cookie_value: str | None = None


class ProfileCompletionService:
    def __init__(self, session: AsyncSession, settings: AuthSettings) -> None:
        self._session = session
        self._settings = settings
        self._repo = AuthenticationRepository(session)
        self._users = RegistrationService(session)

    async def complete(
        self,
        *,
        cookie_value: str | None,
        nickname: str,
        role: str,
        idempotency_key: str | None,
        request_id: str,
        client_ip: str | None = None,
    ) -> ProfileCompleteResult:
        parsed = parse_profile_cookie(cookie_value)
        if parsed is None:
            return ProfileCompleteResult(
                kind="unauthenticated",
                http_status=401,
                code="AUTH_VERIFICATION_REQUIRED",
                message=MSG_AUTH_VERIFICATION_REQUIRED,
            )
        key_version, opaque = parsed
        session_mat = self._settings.key_material("session")
        csrf_mat = self._settings.key_material("csrf")
        key = session_mat.resolve(key_version)
        if (
            key is None
            or not session_mat.current_usable()
            or not csrf_mat.current_usable()
        ):
            return ProfileCompleteResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )
        digest = profile_token_digest(key, opaque)
        now = utc_now()
        intent = await self._repo.get_open_intent_by_digest(digest, now=now)
        if intent is None:
            await self._repo.rollback()
            return ProfileCompleteResult(
                kind="unauthenticated",
                http_status=401,
                code="PROFILE_EXPIRED",
                message=MSG_PROFILE_EXPIRED,
            )

        created = await self._users.register(
            phone=intent.phone_normalized,
            nickname=nickname,
            role=role,
            idempotency_key=idempotency_key,
            commit=False,
        )
        if created.kind != "success":
            await self._repo.rollback()
            return ProfileCompleteResult(
                kind="conflict" if created.http_status == 409 else "validation",
                http_status=created.http_status,
                code=created.code,
                message=created.message,
                data=created.data,
            )

        user_id = uuid.UUID(str(created.data["user_id"]))
        user = await self._repo.lock_user_by_id(user_id)
        if user is None:
            await self._repo.rollback()
            return ProfileCompleteResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )

        intent.consumed_at = now
        generation = await self._repo.bump_session_generation(user)
        ref_mat = self._settings.key_material("reference")
        hint = (
            client_hint(ref_mat.current, client_ip)
            if ref_mat.current_usable()
            else None
        )
        token = generate_session_token(session_mat.version)
        sdigest = token_digest(session_mat.current, token.opaque_secret)
        session_id = uuid.uuid4()
        try:
            auth_session = await self._repo.insert_session(
                session_id=session_id,
                user_id=user.id,
                token_digest=sdigest,
                token_key_version=session_mat.version,
                role_snapshot=user.role,
                created_request_id=request_id,
                now=now,
                session_generation=generation,
                client_hint=hint,
            )
        except IntegrityError:
            await self._repo.rollback()
            return ProfileCompleteResult(
                kind="service_unavailable",
                http_status=503,
                code="SERVICE_UNAVAILABLE",
                message=MSG_SERVICE_UNAVAILABLE,
            )
        csrf = issue_csrf_token(csrf_mat.current, csrf_mat.version, auth_session.id)
        await self._repo.append_security_event(
            event_type="profile_completed",
            outcome="success",
            reason_code="register",
            request_id=request_id,
            user_id=user.id,
            now=now,
        )
        try:
            await self._repo.commit()
        except IntegrityError:
            await self._repo.rollback()
            return ProfileCompleteResult(
                kind="conflict",
                http_status=409,
                code="PHONE_ALREADY_REGISTERED",
                message="该手机号已被注册",
            )

        expires = auth_session.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return ProfileCompleteResult(
            kind="success",
            http_status=200,
            code="0",
            message="success",
            data={
                "user_id": str(user.id),
                "nickname": user.nickname,
                "phone_masked": mask_phone(user.phone_normalized),
                "role": (
                    user.role.value if hasattr(user.role, "value") else str(user.role)
                ),
                "expires_at": expires,
                "csrf_token": csrf,
            },
            cookie_value=token.cookie_value,
        )
