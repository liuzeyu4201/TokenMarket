"""Origin + session-bound CSRF for cookie-authenticated key-lifecycle writes."""

from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.dependencies import get_auth_settings
from app.errors import MSG_CSRF_INVALID, MSG_ORIGIN_REJECTED
from app.observability import record_auth_csrf_rejected
from app.schemas.envelope import error_envelope
from app.security.csrf import verify_csrf_token
from app.security.origin import origin_allowed
from app.security.session import SESSION_COOKIE_NAME

_DEFAULT_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://127.0.0.1:5173",
    "https://localhost:5173",
)

_FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _allowed_origins(request: Request) -> list[str]:
    settings = get_auth_settings(request)
    origins = settings.browser_origin_list
    return origins if origins else list(_DEFAULT_ORIGINS)


def guard_cookie_mutation(
    request: Request,
    *,
    session_id: uuid.UUID | None,
    origin: str | None = None,
    csrf_presented: str | None = None,
) -> JSONResponse | None:
    """Reject cookie-authenticated mutations with bad Origin or CSRF.

    Non-browser callers (no session cookie) are unchanged. Form content types
    are rejected because these routes require JSON bodies.
    """
    rid = _request_id(request)
    content_type = (request.headers.get("content-type") or "").lower()
    if any(form in content_type for form in _FORM_TYPES):
        return JSONResponse(
            status_code=415,
            content=error_envelope(
                "INVALID_REQUEST", "需要 JSON 请求体", request_id=rid
            ),
        )

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None

    origin_value = origin
    if origin_value is None:
        origin_value = request.headers.get("origin") or request.headers.get("Origin")
    csrf_value = csrf_presented
    if csrf_value is None:
        csrf_value = request.headers.get("x-csrf-token") or request.headers.get(
            "X-CSRF-Token"
        )

    if not origin_allowed(origin_value, _allowed_origins(request)):
        record_auth_csrf_rejected("origin")
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "ORIGIN_REJECTED", MSG_ORIGIN_REJECTED, request_id=rid
            ),
        )
    if session_id is None:
        record_auth_csrf_rejected("csrf")
        return JSONResponse(
            status_code=403,
            content=error_envelope("CSRF_INVALID", MSG_CSRF_INVALID, request_id=rid),
        )
    settings = get_auth_settings(request)
    csrf_mat = settings.key_material("csrf")
    versions = [csrf_mat.version]
    if csrf_mat.previous is not None and csrf_mat.version > 1:
        versions.append(csrf_mat.version - 1)
    for ver in versions:
        key = csrf_mat.resolve(ver)
        if verify_csrf_token(key, ver, session_id, csrf_value):
            return None
    record_auth_csrf_rejected("csrf")
    return JSONResponse(
        status_code=403,
        content=error_envelope("CSRF_INVALID", MSG_CSRF_INVALID, request_id=rid),
    )
