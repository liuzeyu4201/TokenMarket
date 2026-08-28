"""Fail-closed shared crypto material (no random fallback, no zero-pad)."""

from __future__ import annotations

import pytest

from app.domain.proxykeys.service import ProxyKeyService
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.security.shared_secrets import (
    SharedSecretError,
    load_process_shared_secrets,
    load_seller_key_version,
    load_shared_secret_bytes,
)


def test_same_deployment_secret_keeps_proxy_and_seller_keys_usable() -> None:
    secret = "aa" * 32
    pepper = load_shared_secret_bytes("PROXY_AUTH_PEPPER", secret)
    material = load_shared_secret_bytes("SELLER_KEY_MATERIAL", secret)
    svc1 = ProxyKeyService(pepper)
    issued = svc1.issue(buyer_id=__import__("uuid").uuid4())
    assert issued.secret_once is not None
    svc2 = ProxyKeyService(pepper, store=svc1._store)
    assert svc2.authenticate(issued.secret_once) is not None
    enc1 = CredentialEncryptor(material, "v1")
    nonce, ct, tag = enc1.encrypt(b"sk-synthetic-test-key-not-real")
    enc2 = CredentialEncryptor(material, "v1")
    assert enc2.decrypt(nonce, ct, tag) == b"sk-synthetic-test-key-not-real"
    duplicate = enc2.encrypt(b"sk-synthetic-test-key-not-real")
    assert duplicate[1] != ct  # nonce uniqueness still rejects naive reuse


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, "SECRET_MISSING"),
        ("", "SECRET_MISSING"),
        ("   ", "SECRET_MISSING"),
        ("not-hex-and-too-short", "SECRET_UNDERSIZED"),
        ("aa" * 16, "SECRET_UNDERSIZED"),  # 16 decoded bytes
        ("abc", "SECRET_MALFORMED"),
    ],
)
def test_missing_malformed_undersized_material_fails(raw: str | None, code: str) -> None:
    with pytest.raises(SharedSecretError) as exc:
        load_shared_secret_bytes("PROXY_AUTH_PEPPER", raw)
    assert exc.value.code == code


def test_unknown_and_mismatched_version_fails() -> None:
    with pytest.raises(SharedSecretError) as missing:
        load_seller_key_version(None)
    assert missing.value.code == "SECRET_VERSION_MISSING"
    with pytest.raises(SharedSecretError) as unknown:
        load_seller_key_version("v99")
    assert unknown.value.code == "SECRET_VERSION_UNKNOWN"
    with pytest.raises(SharedSecretError) as malformed:
        load_seller_key_version("v1/../etc")
    assert malformed.value.code == "SECRET_VERSION_MALFORMED"
    env = {
        "SELLER_KEY_MATERIAL": "11" * 32,
        "SELLER_KEY_FINGERPRINT_SECRET": "22" * 32,
        "PROXY_AUTH_PEPPER": "33" * 32,
        "SELLER_KEY_VERSION": "v2",
    }
    with pytest.raises(SharedSecretError):
        load_process_shared_secrets(env)
