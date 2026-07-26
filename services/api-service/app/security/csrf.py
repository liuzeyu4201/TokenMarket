"""Session-bound deterministic CSRF tokens (versioned HMAC)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from typing import Final

_CSRF_DOMAIN: Final[bytes] = b"csrf:v1"


def _session_id_bytes(session_id: uuid.UUID | str | bytes) -> bytes:
    if isinstance(session_id, uuid.UUID):
        return session_id.bytes
    if isinstance(session_id, bytes):
        if len(session_id) == 16:
            return session_id
        return uuid.UUID(session_id.decode("ascii")).bytes
    return uuid.UUID(str(session_id)).bytes


def issue_csrf_token(key: bytes, key_version: int, session_id: uuid.UUID | str | bytes) -> str:
    """Compute versioned HMAC bound to *session_id*; return wire form.

    Format: ``<key-version>.<urlsafe-base64-hmac>``.
    """
    if not key:
        raise ValueError("CSRF HMAC key must not be empty")
    if key_version < 1:
        raise ValueError("key_version must be >= 1")
    sid = _session_id_bytes(session_id)
    mac = hmac.new(key, _CSRF_DOMAIN + sid, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")
    return f"{key_version}.{encoded}"


def verify_csrf_token(
    key: bytes | None,
    key_version: int,
    session_id: uuid.UUID | str | bytes,
    presented: str | None,
) -> bool:
    """Constant-time verify of a session-bound CSRF token.

    *key* is the material for *key_version* already resolved by the caller.
    Unknown version (``key is None``) fails closed.
    """
    if key is None or not presented or not isinstance(presented, str):
        return False
    if "." not in presented:
        return False
    version_s, _rest = presented.split(".", 1)
    if not version_s.isdigit() or int(version_s) != key_version:
        return False
    try:
        expected = issue_csrf_token(key, key_version, session_id)
    except ValueError:
        return False
    return hmac.compare_digest(expected, presented)
