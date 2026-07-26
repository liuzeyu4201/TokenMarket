"""Authentication cryptography and request-source security primitives."""

from __future__ import annotations

from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.otp import derive_otp, otp_verification_digest, verify_otp_digest
from app.security.reference import idempotency_key_digest, phone_ref
from app.security.session import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    clear_session_cookie,
    generate_session_token,
    parse_session_cookie,
    set_session_cookie,
    token_digest,
)
from app.security.trusted_proxy import resolve_client_ip

__all__ = [
    "SESSION_COOKIE_NAME",
    "SESSION_MAX_AGE_SECONDS",
    "clear_session_cookie",
    "derive_otp",
    "generate_session_token",
    "idempotency_key_digest",
    "issue_csrf_token",
    "otp_verification_digest",
    "parse_session_cookie",
    "phone_ref",
    "resolve_client_ip",
    "set_session_cookie",
    "token_digest",
    "verify_csrf_token",
    "verify_otp_digest",
]
