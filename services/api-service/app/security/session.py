"""Opaque session token generation, digest, and __Host- cookie helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Final

from starlette.responses import Response

SESSION_COOKIE_NAME: Final[str] = "__Host-tokenmarket_session"
SESSION_MAX_AGE_SECONDS: Final[int] = 3600
OPAQUE_SECRET_BYTES: Final[int] = 32  # 256-bit CSPRNG
_SESSION_DOMAIN: Final[bytes] = b"session-token:v1"


@dataclass(frozen=True)
class SessionToken:
    """Issued session credential material (never log or persist the secret)."""

    key_version: int
    opaque_secret: str
    cookie_value: str
    raw_secret_bytes: bytes


def generate_session_token(key_version: int) -> SessionToken:
    """Generate a 256-bit opaque secret and versioned cookie value."""
    if key_version < 1:
        raise ValueError("key_version must be >= 1")
    raw = secrets.token_bytes(OPAQUE_SECRET_BYTES)
    opaque = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    cookie_value = f"{key_version}.{opaque}"
    return SessionToken(
        key_version=key_version,
        opaque_secret=opaque,
        cookie_value=cookie_value,
        raw_secret_bytes=raw,
    )


def parse_session_cookie(cookie_value: str | None) -> tuple[int, str] | None:
    """Parse ``<key-version>.<opaque-secret>``; return None if malformed."""
    if not cookie_value or not isinstance(cookie_value, str):
        return None
    if cookie_value.count(".") < 1:
        return None
    version_s, opaque = cookie_value.split(".", 1)
    if not version_s.isdigit() or not opaque:
        return None
    version = int(version_s)
    if version < 1:
        return None
    # Opaque must be non-empty urlsafe base64-ish material.
    if any(ch.isspace() for ch in opaque):
        return None
    return version, opaque


def token_digest(key: bytes, opaque_secret: str | bytes) -> bytes:
    """HMAC-SHA-256 digest of the opaque secret for DB storage."""
    if not key:
        raise ValueError("session HMAC key must not be empty")
    if isinstance(opaque_secret, str):
        raw = opaque_secret.encode("ascii")
    else:
        raw = opaque_secret
    if not raw:
        raise ValueError("opaque secret must not be empty")
    return hmac.new(key, _SESSION_DOMAIN + raw, hashlib.sha256).digest()


def set_session_cookie(
    response: Response,
    cookie_value: str,
    *,
    max_age: int = SESSION_MAX_AGE_SECONDS,
) -> None:
    """Issue the session cookie with required __Host- attributes."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
        # Domain must be absent for __Host- prefix.
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie with the exact same scope as issue."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value="",
        max_age=0,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
