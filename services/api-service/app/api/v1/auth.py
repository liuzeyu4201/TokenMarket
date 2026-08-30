"""Authentication HTTP routes: register, verification-challenges, sessions."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_rate_limit import AuthRateLimiter
from app.config import AuthSettings
from app.dependencies import (
    client_ip,
    get_auth_rate_limiter,
    get_auth_settings,
    get_db_session,
    get_rate_limiter,
)
from app.domain.authentication.challenge_service import ChallengeService
from app.domain.authentication.profile_service import ProfileCompletionService
from app.domain.authentication.session_service import SessionService
from app.errors import (
    MSG_AUTH_VERIFICATION_REQUIRED,
    MSG_CSRF_INVALID,
    MSG_ORIGIN_REJECTED,
    MSG_RATE_LIMITED,
)
from app.observability import (
    emit_auth_event,
    record_auth_challenge,
    record_auth_csrf_rejected,
    record_rate_limit_backend_unavailable,
    record_rate_limited,
    record_registration_attempt,
)
from app.rate_limit import RateLimitBackendUnavailable, RateLimiter
from app.schemas.authentication import (
    CompleteProfileRequest,
    CreateSessionRequest,
    RequestChallengeRequest,
)
from app.schemas.envelope import error_envelope, success_envelope
from app.security.origin import origin_allowed
from app.security.profile_token import (
    PROFILE_COOKIE_NAME,
    clear_profile_cookie,
    set_profile_cookie,
)
from app.security.session import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    set_session_cookie,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger("api-service")


def _default_origins() -> list[str]:
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "https://127.0.0.1:5173",
        "https://localhost:5173",
    ]


def _allowed_origins(settings: AuthSettings) -> list[str]:
    origins = settings.browser_origin_list
    return origins if origins else _default_origins()


def _origin_rejected(origin: str | None, settings: AuthSettings) -> bool:
    if origin_allowed(origin, _allowed_origins(settings)):
        return False
    record_auth_csrf_rejected("origin")
    emit_auth_event(logger, "auth.origin.rejected", reason="origin")
    return True


def _serialize_data(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
    return data


@router.post("/register")
async def register_user(
    request: Request,
) -> JSONResponse:
    """V0.2：无 OTP 补全凭证的公开注册一律拒绝，避免占用冲突枚举。"""
    request_id = getattr(request.state, "request_id", "unknown")
    record_registration_attempt("verification_required")
    return JSONResponse(
        status_code=403,
        content=error_envelope(
            "AUTH_VERIFICATION_REQUIRED",
            MSG_AUTH_VERIFICATION_REQUIRED,
            request_id=request_id,
        ),
    )


@router.post("/profile-completions")
async def complete_profile(
    body: CompleteProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
    settings: AuthSettings = Depends(get_auth_settings),
    origin: str | None = Header(default=None, alias="Origin"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    if _origin_rejected(origin, settings):
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "ORIGIN_REJECTED",
                MSG_ORIGIN_REJECTED,
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )
    ip = client_ip(request)
    try:
        decision = await limiter.check_and_increment(ip=ip, phone_normalized=None)
    except RateLimitBackendUnavailable:
        record_rate_limit_backend_unavailable()
        return JSONResponse(
            status_code=503,
            content=error_envelope(
                "SERVICE_UNAVAILABLE",
                "服务暂时不可用，请稍后重试",
                request_id=request_id,
            ),
        )
    if not decision.allowed:
        record_rate_limited()
        return JSONResponse(
            status_code=429,
            content=error_envelope(
                "RATE_LIMITED",
                MSG_RATE_LIMITED,
                request_id=request_id,
            ),
        )
    service = ProfileCompletionService(session, settings)
    result = await service.complete(
        cookie_value=request.cookies.get(PROFILE_COOKIE_NAME),
        nickname=body.nickname,
        role=body.role,
        idempotency_key=idempotency_key,
        request_id=request_id,
    )
    if result.kind == "success":
        response = JSONResponse(
            status_code=200,
            content=success_envelope(
                _serialize_data(result.data), request_id=request_id
            ),
            headers={"Cache-Control": "no-store"},
        )
        if result.cookie_value:
            set_session_cookie(response, result.cookie_value)
        clear_profile_cookie(response)
        return response
    return JSONResponse(
        status_code=result.http_status,
        content=error_envelope(
            result.code,
            result.message,
            request_id=request_id,
            data=_serialize_data(result.data),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/verification-challenges")
async def request_verification_challenge(
    body: RequestChallengeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: AuthSettings = Depends(get_auth_settings),
    auth_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    origin: str | None = Header(default=None, alias="Origin"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    start = time.monotonic()
    ip = client_ip(request)

    if _origin_rejected(origin, settings):
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "ORIGIN_REJECTED",
                MSG_ORIGIN_REJECTED,
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    sms = getattr(request.app.state, "sms_adapter", None)
    provider_ok = True
    if sms is not None and hasattr(sms, "provider_health_ok"):
        try:
            provider_ok = bool(sms.provider_health_ok())
        except Exception:  # noqa: BLE001
            provider_ok = False

    service = ChallengeService(
        session,
        settings,
        provider_health_ok=provider_ok,
        rate_limiter=auth_limiter,
    )
    try:
        result = await service.request_challenge(
            phone=body.phone,
            idempotency_key=idempotency_key,
            request_id=request_id,
            client_ip=ip,
        )
    except Exception:
        logger.exception("challenge request failed", extra={"request_id": request_id})
        record_auth_challenge("internal_error", time.monotonic() - start)
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "INTERNAL_ERROR",
                "内部错误",
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    duration = time.monotonic() - start
    metric_result = (
        "accepted" if result.code == "0" else result.code.lower().replace(" ", "_")[:64]
    )
    record_auth_challenge(metric_result, duration)
    if result.code == "0":
        emit_auth_event(
            logger,
            "auth.challenge.accepted",
            request_id=request_id,
        )
    elif result.code == "DELIVERY_UNAVAILABLE":
        emit_auth_event(
            logger,
            "auth.challenge.delivery_unavailable",
            request_id=request_id,
        )
    elif result.code == "RATE_LIMITED":
        # Metric is recorded once at first rate-limit decision (not on replay).
        emit_auth_event(
            logger,
            "auth.challenge.rate_limited",
            request_id=request_id,
        )

    headers: dict[str, str] = {"Cache-Control": "no-store"}
    if result.code == "RATE_LIMITED":
        retry = result.retry_after_seconds
        if retry is None and isinstance(result.data, dict):
            retry = result.data.get("retry_after_seconds")
        retry_int = max(1, int(retry or 1))
        headers["Retry-After"] = str(retry_int)
        data = result.data if isinstance(result.data, dict) else {}
        if "retry_after_seconds" not in data:
            data = {**data, "retry_after_seconds": retry_int}
        return JSONResponse(
            status_code=429,
            content=error_envelope(
                "RATE_LIMITED",
                result.message or MSG_RATE_LIMITED,
                request_id=request_id,
                data=data,
            ),
            headers=headers,
        )

    if result.code == "0":
        return JSONResponse(
            status_code=result.http_status,
            content=success_envelope(
                _serialize_data(result.data),
                request_id=request_id,
                message=result.message,
            ),
            headers=headers,
        )

    return JSONResponse(
        status_code=result.http_status,
        content=error_envelope(
            result.code,
            result.message,
            request_id=request_id,
            data=_serialize_data(result.data),
        ),
        headers=headers,
    )


@router.post("/sessions")
async def create_authenticated_session(
    body: CreateSessionRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: AuthSettings = Depends(get_auth_settings),
    origin: str | None = Header(default=None, alias="Origin"),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")

    if _origin_rejected(origin, settings):
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "ORIGIN_REJECTED",
                MSG_ORIGIN_REJECTED,
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    service = SessionService(session, settings)
    try:
        result = await service.create_session(
            challenge_id=body.challenge_id,
            code=body.code,
            request_id=request_id,
        )
    except Exception:
        logger.exception("session create failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "INTERNAL_ERROR",
                "内部错误",
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    if result.kind == "success":
        response = JSONResponse(
            status_code=200,
            content=success_envelope(
                _serialize_data(result.data),
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )
        if result.cookie_value:
            set_session_cookie(response, result.cookie_value)
        return response

    if result.kind == "profile_completion":
        response = JSONResponse(
            status_code=200,
            content=error_envelope(
                result.code,
                result.message,
                request_id=request_id,
                data=_serialize_data(result.data),
            ),
            headers={"Cache-Control": "no-store"},
        )
        if result.profile_cookie_value:
            set_profile_cookie(response, result.profile_cookie_value)
        return response

    return JSONResponse(
        status_code=result.http_status,
        content=error_envelope(
            result.code,
            result.message,
            request_id=request_id,
            data=_serialize_data(result.data),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/session")
async def get_current_session(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> JSONResponse:
    """Bootstrap current browser session from the HttpOnly cookie."""
    request_id = getattr(request.state, "request_id", "unknown")
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)

    service = SessionService(session, settings)
    try:
        result = await service.bootstrap_session(
            cookie_value=cookie_value,
            request_id=request_id,
        )
    except Exception:
        logger.exception("session bootstrap failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "INTERNAL_ERROR",
                "内部错误",
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    if result.kind == "success":
        return JSONResponse(
            status_code=200,
            content=success_envelope(
                _serialize_data(result.data),
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    response = JSONResponse(
        status_code=result.http_status,
        content=error_envelope(
            result.code,
            result.message,
            request_id=request_id,
        ),
        headers={"Cache-Control": "no-store"},
    )
    if result.clear_cookie:
        clear_session_cookie(response)
    return response


@router.delete("/session")
async def delete_current_session(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: AuthSettings = Depends(get_auth_settings),
    origin: str | None = Header(default=None, alias="Origin"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> JSONResponse:
    """Idempotently revoke the exact current session cookie."""
    request_id = getattr(request.state, "request_id", "unknown")
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)

    # Browser write path: Origin must be allowlisted when a cookie may be present.
    if origin is not None or cookie_value:
        if _origin_rejected(origin, settings):
            return JSONResponse(
                status_code=403,
                content=error_envelope(
                    "ORIGIN_REJECTED",
                    MSG_ORIGIN_REJECTED,
                    request_id=request_id,
                ),
                headers={"Cache-Control": "no-store"},
            )

    service = SessionService(session, settings)
    try:
        result = await service.logout_session(
            cookie_value=cookie_value,
            csrf_presented=csrf_token,
            request_id=request_id,
        )
    except Exception:
        logger.exception("session logout failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "INTERNAL_ERROR",
                "内部错误",
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    if result.kind == "csrf_invalid":
        record_auth_csrf_rejected("csrf")
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "CSRF_INVALID",
                MSG_CSRF_INVALID,
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    if result.kind == "service_unavailable":
        return JSONResponse(
            status_code=503,
            content=error_envelope(
                result.code,
                result.message,
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    response = JSONResponse(
        status_code=200,
        content=success_envelope(
            _serialize_data(result.data) or {"logged_out": True},
            request_id=request_id,
        ),
        headers={"Cache-Control": "no-store"},
    )
    if result.clear_cookie:
        clear_session_cookie(response)
    return response
