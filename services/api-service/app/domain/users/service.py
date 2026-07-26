"""Registration domain service."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import UserRole
from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile
from app.domain.users.privacy import mask_phone
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.users import UserRepository

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class FieldErrors:
    errors: dict[str, list[str]]


@dataclass
class RegisterResult:
    kind: Literal[
        "success",
        "validation",
        "phone_taken",
        "account_unavailable",
        "idempotency_conflict",
        "idempotency_expired",
        "idempotency_required",
    ]
    http_status: int
    code: str
    message: str
    data: Any = None


def _request_hash(phone_normalized: str, nickname: str, role: str) -> str:
    canonical = f"{phone_normalized}|{nickname}|{role}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_nickname(raw: str) -> str | FieldErrors:
    stripped = raw.strip()
    if not stripped or len(stripped) > 50 or _CONTROL.search(stripped):
        return FieldErrors(
            errors={"nickname": ["昵称长度须为 1–50 个可显示字符，且不得包含控制字符"]}
        )
    return stripped


def _validate_idempotency_key(key: str | None) -> str | RegisterResult:
    if key is None or not key.strip() or len(key.strip()) > 64:
        return RegisterResult(
            kind="idempotency_required",
            http_status=400,
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="缺少或无效的幂等键",
        )
    return key.strip()


class RegistrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._idem = IdempotencyRepository(session)

    async def register(
        self,
        *,
        phone: str,
        nickname: str,
        role: str,
        idempotency_key: str | None,
    ) -> RegisterResult:
        key_or_err = _validate_idempotency_key(idempotency_key)
        if isinstance(key_or_err, RegisterResult):
            return key_or_err
        key = key_or_err

        if role not in ("buyer", "seller", "both"):
            return RegisterResult(
                kind="validation",
                http_status=400,
                code="VALIDATION_ERROR",
                message="请求参数不合法",
                data={"errors": {"role": ["角色必须是 buyer、seller 或 both"]}},
            )

        nick = _validate_nickname(nickname)
        phone_result = normalize_cn_mobile(phone)
        field_errors: dict[str, list[str]] = {}
        if isinstance(nick, FieldErrors):
            field_errors.update(nick.errors)
        if isinstance(phone_result, PhoneValidationError):
            field_errors.setdefault("phone", []).append(phone_result.message)
        if field_errors:
            return RegisterResult(
                kind="validation",
                http_status=400,
                code="VALIDATION_ERROR",
                message="请求参数不合法",
                data={"errors": field_errors},
            )
        assert isinstance(nick, str)
        assert isinstance(phone_result, str)
        phone_normalized = phone_result
        req_hash = _request_hash(phone_normalized, nick, role)

        existing_idem = await self._idem.get(key)
        if existing_idem is not None:
            now = datetime.now(timezone.utc)
            exp = existing_idem.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now >= exp:
                return RegisterResult(
                    kind="idempotency_expired",
                    http_status=409,
                    code="IDEMPOTENCY_KEY_EXPIRED",
                    message="幂等键已过期，请使用新键重试",
                )
            if existing_idem.request_hash != req_hash:
                return RegisterResult(
                    kind="idempotency_conflict",
                    http_status=409,
                    code="IDEMPOTENCY_KEY_CONFLICT",
                    message="幂等键与请求内容不一致",
                )
            return RegisterResult(
                kind="success",
                http_status=200,
                code="0",
                message="success",
                data=existing_idem.result_payload,
            )

        existing_user = await self._users.get_by_phone(phone_normalized)
        if existing_user is not None:
            if existing_user.is_deleted:
                return RegisterResult(
                    kind="account_unavailable",
                    http_status=409,
                    code="ACCOUNT_UNAVAILABLE",
                    message="账户不可用，请通过恢复流程处理",
                )
            return RegisterResult(
                kind="phone_taken",
                http_status=409,
                code="PHONE_ALREADY_REGISTERED",
                message="该手机号已被注册",
            )

        try:
            user = await self._users.create(
                phone_normalized=phone_normalized,
                nickname=nick,
                role=UserRole(role),
            )
            payload = {
                "user_id": str(user.id),
                "role": user.role.value,
                "status": "active",
                "created_at": (
                    user.created_at.isoformat()
                    if user.created_at.tzinfo
                    else user.created_at.replace(tzinfo=timezone.utc).isoformat()
                ),
                "phone_masked": mask_phone(phone_normalized),
            }
            await self._idem.create(
                key=key,
                request_hash=req_hash,
                user_id=user.id,
                result_code="0",
                result_payload=payload,
            )
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            # Concurrent create or unique race
            raced = await self._users.get_by_phone(phone_normalized)
            if raced is not None and raced.is_deleted:
                return RegisterResult(
                    kind="account_unavailable",
                    http_status=409,
                    code="ACCOUNT_UNAVAILABLE",
                    message="账户不可用，请通过恢复流程处理",
                )
            # Idempotency key race: re-read
            raced_idem = await self._idem.get(key)
            if raced_idem is not None and raced_idem.request_hash == req_hash:
                return RegisterResult(
                    kind="success",
                    http_status=200,
                    code="0",
                    message="success",
                    data=raced_idem.result_payload,
                )
            return RegisterResult(
                kind="phone_taken",
                http_status=409,
                code="PHONE_ALREADY_REGISTERED",
                message="该手机号已被注册",
            )

        return RegisterResult(
            kind="success",
            http_status=200,
            code="0",
            message="success",
            data=payload,
        )
