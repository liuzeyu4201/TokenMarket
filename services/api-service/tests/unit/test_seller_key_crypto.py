"""Seller Key AEAD and fingerprint (SF08)."""

from __future__ import annotations

import os

import pytest

from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.fingerprint import fingerprint_key, normalize_key


def test_encrypt_roundtrip_and_tamper() -> None:
    enc = CredentialEncryptor(os.urandom(32), "v1")
    nonce, ct, tag = enc.encrypt(b"sk-synthetic-test-key-not-real")
    assert enc.decrypt(nonce, ct, tag) == b"sk-synthetic-test-key-not-real"
    with pytest.raises(ValueError, match="authentication"):
        enc.decrypt(nonce, ct, tag[:-1] + bytes([tag[-1] ^ 1]))
    with pytest.raises(ValueError):
        enc.decrypt(nonce, bytes([ct[0] ^ 1]) + ct[1:], tag)


def test_fingerprint_stable_and_irreversible() -> None:
    secret = b"x" * 32
    a = fingerprint_key(" sk-abc ", secret)
    b = fingerprint_key("sk-abc", secret)
    assert a == b
    assert "sk-abc" not in a
    assert fingerprint_key("sk-abc", secret, platform="volcano") != fingerprint_key(
        "sk-abc", secret, platform="other"
    )
    assert normalize_key(" a ") == "a"


def test_short_key_material_rejected() -> None:
    with pytest.raises(ValueError):
        CredentialEncryptor(b"short", "v1")
