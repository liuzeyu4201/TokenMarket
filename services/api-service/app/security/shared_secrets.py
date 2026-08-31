"""Fail-closed loading of shared crypto material (pepper, AEAD, fingerprint)."""

from __future__ import annotations

import os
import re

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
ALLOWED_SELLER_KEY_VERSIONS = frozenset({"v1", "v2"})
MIN_SECRET_BYTES = 32


class SharedSecretError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def load_shared_secret_bytes(name: str, raw: str | None) -> bytes:
    """Load a named shared secret.

    Accepts even-length hex of at least 32 decoded bytes, or raw UTF-8 of at
    least 32 bytes. Missing, malformed, or undersized material fails closed.
    Never generates process-local random keys and never zero-pads.
    """
    text = (raw or "").strip()
    if not text:
        raise SharedSecretError(
            "SECRET_MISSING",
            f"{name} is required; refuse silent random or empty material",
        )
    if _HEX_RE.fullmatch(text):
        if len(text) % 2 != 0:
            raise SharedSecretError(
                "SECRET_MALFORMED",
                f"{name} hex material must have even length",
            )
        decoded = bytes.fromhex(text)
        if len(decoded) < MIN_SECRET_BYTES:
            raise SharedSecretError(
                "SECRET_UNDERSIZED",
                f"{name} must be at least {MIN_SECRET_BYTES} bytes",
            )
        return decoded
    encoded = text.encode("utf-8")
    if len(encoded) < MIN_SECRET_BYTES:
        raise SharedSecretError(
            "SECRET_UNDERSIZED",
            f"{name} must be at least {MIN_SECRET_BYTES} bytes",
        )
    return encoded


def load_seller_key_version(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        raise SharedSecretError(
            "SECRET_VERSION_MISSING",
            "SELLER_KEY_VERSION is required",
        )
    if not _VERSION_RE.fullmatch(text):
        raise SharedSecretError(
            "SECRET_VERSION_MALFORMED",
            "SELLER_KEY_VERSION is malformed",
        )
    if text not in ALLOWED_SELLER_KEY_VERSIONS:
        raise SharedSecretError(
            "SECRET_VERSION_UNKNOWN",
            f"SELLER_KEY_VERSION {text!r} is not in the allowed key ring",
        )
    return text


def load_seller_previous_keys(
    environ: dict[str, str] | None = None,
) -> dict[str, bytes]:
    """Load optional previous ring members (SELLER_KEY_MATERIAL_PREVIOUS)."""
    env = os.environ if environ is None else environ
    prev_ver = (env.get("SELLER_KEY_PREVIOUS_VERSION") or "").strip()
    prev_raw = (env.get("SELLER_KEY_MATERIAL_PREVIOUS") or "").strip()
    if not prev_ver and not prev_raw:
        return {}
    if not prev_ver or not prev_raw:
        raise SharedSecretError(
            "SECRET_VERSION_MISSING",
            "SELLER_KEY_PREVIOUS_VERSION and "
            "SELLER_KEY_MATERIAL_PREVIOUS must be set together",
        )
    version = load_seller_key_version(prev_ver)
    material = load_shared_secret_bytes("SELLER_KEY_MATERIAL_PREVIOUS", prev_raw)
    return {version: material}


def load_process_shared_secrets(
    environ: dict[str, str] | None = None,
) -> tuple[bytes, bytes, bytes, str, dict[str, bytes]]:
    """Load seller material, fingerprint secret, pepper, version, previous."""
    env: dict[str, str] = dict(os.environ if environ is None else environ)
    material = load_shared_secret_bytes(
        "SELLER_KEY_MATERIAL", env.get("SELLER_KEY_MATERIAL")
    )
    fingerprint = load_shared_secret_bytes(
        "SELLER_KEY_FINGERPRINT_SECRET", env.get("SELLER_KEY_FINGERPRINT_SECRET")
    )
    pepper = load_shared_secret_bytes("PROXY_AUTH_PEPPER", env.get("PROXY_AUTH_PEPPER"))
    version = load_seller_key_version(env.get("SELLER_KEY_VERSION"))
    previous = load_seller_previous_keys(env)
    previous.pop(version, None)
    return material, fingerprint, pepper, version, previous
