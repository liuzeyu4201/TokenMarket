"""Host-only profile-completion cookie (not a session)."""

from __future__ import annotations

from typing import Final

from starlette.responses import Response

from app.security.session import (
    SessionToken,
    generate_session_token,
    parse_session_cookie,
    token_digest,
)

PROFILE_COOKIE_NAME: Final[str] = "__Host-tokenmarket_profile"
PROFILE_MAX_AGE_SECONDS: Final[int] = 600
_PROFILE_DOMAIN: Final[bytes] = b"profile-completion:v1"


def generate_profile_token(key_version: int) -> SessionToken:
    return generate_session_token(key_version)


def parse_profile_cookie(cookie_value: str | None) -> tuple[int, str] | None:
    return parse_session_cookie(cookie_value)


def profile_token_digest(key: bytes, opaque_secret: str | bytes) -> bytes:
    # Reuse HMAC helper but domain-separate via prefixing opaque.
    if isinstance(opaque_secret, str):
        material = _PROFILE_DOMAIN + opaque_secret.encode("ascii")
    else:
        material = _PROFILE_DOMAIN + opaque_secret
    return token_digest(key, material)


def set_profile_cookie(response: Response, cookie_value: str) -> None:
    response.set_cookie(
        key=PROFILE_COOKIE_NAME,
        value=cookie_value,
        max_age=PROFILE_MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_profile_cookie(response: Response) -> None:
    response.set_cookie(
        key=PROFILE_COOKIE_NAME,
        value="",
        max_age=0,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
