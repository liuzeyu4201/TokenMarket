"""POST /api/v1/auth/register — no session/token issuance."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import client_ip, get_db_session, get_rate_limiter
from app.domain.users.phone import PhoneValidationError, normalize_cn_mobile
from app.domain.users.service import RegistrationService
from app.observability import (
    record_rate_limit_backend_unavailable,
    record_rate_limited,
    record_registration_attempt,
    record_registration_duration,
)
from app.rate_limit import RateLimitBackendUnavailable, RateLimiter
from app.schemas.envelope import error_envelope, success_envelope
from app.schemas.register import RegisterRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger("api-service")


@router.post("/register")
async def register_user(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    start = time.monotonic()
    ip = client_ip(request)

    # Rate limit: IP always; phone only after successful normalize (FR-020a)
    phone_norm: str | None = None
    norm = normalize_cn_mobile(body.phone)
    if not isinstance(norm, PhoneValidationError):
        phone_norm = norm

    try:
        decision = await limiter.check_and_increment(ip=ip, phone_normalized=phone_norm)
    except RateLimitBackendUnavailable:
        record_rate_limit_backend_unavailable()
        record_registration_attempt("service_unavailable")
        record_registration_duration(time.monotonic() - start)
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
        record_registration_attempt("rate_limited")
        record_registration_duration(time.monotonic() - start)
        return JSONResponse(
            status_code=429,
            content=error_envelope(
                "RATE_LIMITED",
                "请求过于频繁，请稍后再试",
                request_id=request_id,
            ),
        )

    try:
        service = RegistrationService(session)
        result = await service.register(
            phone=body.phone,
            nickname=body.nickname,
            role=body.role,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception(
            "registration failed",
            extra={"request_id": request_id},
        )
        record_registration_attempt("internal_error")
        record_registration_duration(time.monotonic() - start)
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "INTERNAL_ERROR",
                "内部错误",
                request_id=request_id,
            ),
        )

    record_registration_attempt(result.code.lower() if result.code != "0" else "success")
    record_registration_duration(time.monotonic() - start)

    if result.kind == "success":
        return JSONResponse(
            status_code=200,
            content=success_envelope(result.data, request_id=request_id),
        )

    return JSONResponse(
        status_code=result.http_status,
        content=error_envelope(
            result.code,
            result.message,
            request_id=request_id,
            data=result.data,
        ),
    )
