"""Versioned HMAC-SHA-256 OTP PRF and verification digests.

Delivery codes are derived in-process from challenge id via a domain-separated
PRF with rejection sampling into unbiased six-digit ASCII (000000–999999).
The database stores only a separate verification HMAC digest + salt.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Final

OTP_LENGTH: Final[int] = 6
OTP_MODULUS: Final[int] = 1_000_000
# Largest multiple of 10^6 that fits in 32 bits — rejection sampling threshold.
_REJECTION_LIMIT: Final[int] = (1 << 32) // OTP_MODULUS * OTP_MODULUS
_OTP_SEND_DOMAIN: Final[bytes] = b"otp-send:v1"
_OTP_VERIFY_DOMAIN: Final[bytes] = b"otp-verify:v1"
_MAX_SAMPLE_ATTEMPTS: Final[int] = 64
CODE_SALT_BYTES: Final[int] = 16


def _challenge_bytes(challenge_id: uuid.UUID | str | bytes) -> bytes:
    if isinstance(challenge_id, uuid.UUID):
        return challenge_id.bytes
    if isinstance(challenge_id, bytes):
        if len(challenge_id) == 16:
            return challenge_id
        # Accept ASCII UUID text
        return uuid.UUID(challenge_id.decode("ascii")).bytes
    return uuid.UUID(str(challenge_id)).bytes


def derive_otp(
    key: bytes,
    challenge_id: uuid.UUID | str | bytes,
    *,
    counter: int = 0,
) -> str:
    """Derive a 6-digit ASCII OTP via HMAC-SHA-256 PRF + rejection sampling.

    Message: ``otp-send:v1 || challenge_id || counter`` where counter advances
    only for rejection-sampling retries so the same inputs always yield the
    same code (dispatcher may recompute without storing the plaintext).
    """
    if not key:
        raise ValueError("OTP HMAC key must not be empty")
    cid = _challenge_bytes(challenge_id)
    sample = int(counter)
    if sample < 0:
        raise ValueError("counter must be non-negative")

    for _ in range(_MAX_SAMPLE_ATTEMPTS):
        msg = _OTP_SEND_DOMAIN + cid + sample.to_bytes(8, "big")
        digest = hmac.new(key, msg, hashlib.sha256).digest()
        candidate = int.from_bytes(digest[:4], "big")
        if candidate < _REJECTION_LIMIT:
            return f"{candidate % OTP_MODULUS:06d}"
        sample += 1

    # Cryptographically negligible; surfaces misconfigured keys in tests.
    raise RuntimeError("OTP rejection sampling failed to produce a digit string")


def generate_code_salt() -> bytes:
    """Return a fresh high-entropy salt for the verification digest."""
    return secrets.token_bytes(CODE_SALT_BYTES)


def otp_verification_digest(
    key: bytes,
    challenge_id: uuid.UUID | str | bytes,
    code_salt: bytes,
    code: str,
) -> bytes:
    """HMAC over ``otp-verify:v1 || challenge_id || code_salt || six_ascii_digits``."""
    if not key:
        raise ValueError("OTP HMAC key must not be empty")
    if not code_salt:
        raise ValueError("code_salt must not be empty")
    if not _is_six_digit_ascii(code):
        raise ValueError("code must be exactly six ASCII digits")
    cid = _challenge_bytes(challenge_id)
    msg = _OTP_VERIFY_DOMAIN + cid + code_salt + code.encode("ascii")
    return hmac.new(key, msg, hashlib.sha256).digest()


def verify_otp_digest(
    key: bytes,
    challenge_id: uuid.UUID | str | bytes,
    code_salt: bytes,
    code: str,
    expected_digest: bytes,
) -> bool:
    """Constant-time compare of recomputed verification digest vs stored digest."""
    if not expected_digest:
        return False
    if not _is_six_digit_ascii(code):
        return False
    try:
        actual = otp_verification_digest(key, challenge_id, code_salt, code)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected_digest)


def _is_six_digit_ascii(code: str) -> bool:
    return (
        isinstance(code, str)
        and len(code) == OTP_LENGTH
        and code.isascii()
        and code.isdigit()
    )
