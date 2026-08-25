"""Authenticated encryption for seller provider keys (encrypt-then-MAC).

V0.1 uses SHAKE256 stream + HMAC-SHA256 (stdlib, no extra lock). Ciphertext,
nonce, and tag are stored separately; key material is never persisted with rows.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256, shake_256


class CredentialEncryptor:
    def __init__(self, key_material: bytes, key_version: str) -> None:
        if len(key_material) < 32:
            raise ValueError("key material must be at least 32 bytes")
        self._key = key_material
        self.key_version = key_version

    def encrypt(self, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        nonce = os.urandom(12)
        stream = shake_256(self._key + nonce).digest(len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(self._key, nonce + ciphertext, sha256).digest()
        return nonce, ciphertext, tag

    def decrypt(self, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
        expect = hmac.new(self._key, nonce + ciphertext, sha256).digest()
        if not hmac.compare_digest(expect, tag):
            raise ValueError("authentication failed")
        stream = shake_256(self._key + nonce).digest(len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream))
