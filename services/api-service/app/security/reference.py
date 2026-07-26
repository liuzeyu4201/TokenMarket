"""HMAC digests for irreversible phone and idempotency references."""

from __future__ import annotations

import hashlib
import hmac
from typing import Final

_PHONE_REF_DOMAIN: Final[bytes] = b"phone-ref:v1"
_IDEMPOTENCY_DOMAIN: Final[bytes] = b"idempotency-key:v1"
_IP_REF_DOMAIN: Final[bytes] = b"ip-ref:v1"


def phone_ref(key: bytes, phone_normalized: str) -> bytes:
    """HMAC reference for a normalized phone number (never reversible)."""
    if not key:
        raise ValueError("reference HMAC key must not be empty")
    if not phone_normalized:
        raise ValueError("phone_normalized must not be empty")
    msg = _PHONE_REF_DOMAIN + phone_normalized.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()


def idempotency_key_digest(key: bytes, idempotency_key: str) -> bytes:
    """HMAC digest of a client-supplied idempotency key for durable storage."""
    if not key:
        raise ValueError("reference HMAC key must not be empty")
    if not idempotency_key:
        raise ValueError("idempotency_key must not be empty")
    msg = _IDEMPOTENCY_DOMAIN + idempotency_key.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()


def ip_ref(key: bytes, client_ip: str) -> bytes:
    """HMAC reference for a client IP used in rate-limit keys."""
    if not key:
        raise ValueError("reference HMAC key must not be empty")
    if not client_ip:
        raise ValueError("client_ip must not be empty")
    msg = _IP_REF_DOMAIN + client_ip.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()
