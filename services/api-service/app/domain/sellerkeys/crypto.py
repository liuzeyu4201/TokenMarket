"""Authenticated encryption for seller provider keys (encrypt-then-MAC).

V0.1 uses SHAKE256 stream + HMAC-SHA256 (stdlib, no extra lock). Ciphertext,
nonce, and tag are stored separately; key material is never persisted with rows.
Decrypt selects the ring member matching the row's persisted key_version.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256, shake_256
from typing import Mapping


class CredentialEncryptor:
    def __init__(
        self,
        key_material: bytes,
        key_version: str,
        previous: Mapping[str, bytes] | None = None,
    ) -> None:
        if len(key_material) < 32:
            raise ValueError("key material must be at least 32 bytes")
        self._keys: dict[str, bytes] = {key_version: key_material}
        if previous:
            for ver, material in previous.items():
                if len(material) < 32:
                    raise ValueError("key material must be at least 32 bytes")
                self._keys[ver] = material
        self.key_version = key_version
        self._key = key_material

    def known_versions(self) -> frozenset[str]:
        return frozenset(self._keys)

    def _material(self, key_version: str | None = None) -> bytes:
        ver = key_version or self.key_version
        key = self._keys.get(ver)
        if key is None:
            raise ValueError(f"unknown key version {ver!r}")
        return key

    def encrypt(self, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        key = self._material(self.key_version)
        nonce = os.urandom(12)
        stream = shake_256(key + nonce).digest(len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(key, nonce + ciphertext, sha256).digest()
        return nonce, ciphertext, tag

    def decrypt(
        self,
        nonce: bytes,
        ciphertext: bytes,
        tag: bytes,
        key_version: str | None = None,
    ) -> bytes:
        key = self._material(key_version)
        expect = hmac.new(key, nonce + ciphertext, sha256).digest()
        if not hmac.compare_digest(expect, tag):
            raise ValueError("authentication failed")
        stream = shake_256(key + nonce).digest(len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream))

    def reencrypt(
        self,
        nonce: bytes,
        ciphertext: bytes,
        tag: bytes,
        key_version: str | None,
    ) -> tuple[bytes, bytes, bytes, str, bool]:
        """Decrypt with persisted version and rewrite with the current version."""
        plaintext = self.decrypt(nonce, ciphertext, tag, key_version)
        ver = key_version or self.key_version
        if ver == self.key_version:
            return nonce, ciphertext, tag, ver, False
        n2, c2, t2 = self.encrypt(plaintext)
        return n2, c2, t2, self.key_version, True
