"""Irreversible credential fingerprint (HMAC-SHA256)."""

from __future__ import annotations

import hmac
from hashlib import sha256


def normalize_key(api_key: str) -> str:
    return api_key.strip()


def fingerprint_key(api_key: str, secret: bytes, *, platform: str = "volcano") -> str:
    raw = f"{platform}\n{normalize_key(api_key)}".encode("utf-8")
    return hmac.new(secret, raw, sha256).hexdigest()
