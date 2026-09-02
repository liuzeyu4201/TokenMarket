"""Branch coverage for auth cryptography and trusted-proxy helpers."""

from __future__ import annotations

import uuid

import pytest
from starlette.responses import Response

from app.security.origin import normalize_origin
from app.security.otp import derive_otp, otp_verification_digest, verify_otp_digest
from app.security.profile_token import (
    clear_profile_cookie,
    generate_profile_token,
    profile_token_digest,
    set_profile_cookie,
)
from app.security.reference import (
    client_hint,
    idempotency_key_digest,
    ip_ref,
    phone_ref,
)
from app.security.session import (
    generate_session_token,
    parse_session_cookie,
    token_digest,
)
from app.security.trusted_proxy import resolve_client_ip


def test_otp_rejects_empty_key_and_negative_counter() -> None:
    cid = uuid.uuid4()
    with pytest.raises(ValueError):
        derive_otp(b"", cid)
    with pytest.raises(ValueError):
        derive_otp(b"k" * 32, cid, counter=-1)
    code = derive_otp(b"k" * 32, cid.bytes)
    assert len(code) == 6
    text_id = str(cid).encode("ascii")
    assert derive_otp(b"k" * 32, text_id) == derive_otp(b"k" * 32, cid)
    assert verify_otp_digest(b"k" * 32, cid, b"salt", "123456", b"") is False
    assert verify_otp_digest(b"k" * 32, cid, b"salt", "abc", b"x") is False
    with pytest.raises(ValueError):
        otp_verification_digest(b"k" * 32, cid, b"", "123456")


def test_reference_hmac_rejects_empty_and_hint_fail_closed() -> None:
    key = b"k" * 32
    with pytest.raises(ValueError):
        phone_ref(b"", "13800138000")
    with pytest.raises(ValueError):
        phone_ref(key, "")
    with pytest.raises(ValueError):
        idempotency_key_digest(b"", "idem")
    with pytest.raises(ValueError):
        idempotency_key_digest(key, "")
    with pytest.raises(ValueError):
        ip_ref(b"", "127.0.0.1")
    with pytest.raises(ValueError):
        ip_ref(key, "")
    assert client_hint(key, None) is None
    assert client_hint(b"", "127.0.0.1") is None
    assert isinstance(client_hint(key, "127.0.0.1"), str)


def test_session_and_profile_token_edges() -> None:
    with pytest.raises(ValueError):
        generate_session_token(0)
    assert parse_session_cookie("1. has space") is None
    with pytest.raises(ValueError):
        token_digest(b"", "opaque")
    with pytest.raises(ValueError):
        token_digest(b"k" * 32, b"")
    digest = token_digest(b"k" * 32, b"secret")
    assert len(digest) == 32
    token = generate_profile_token(1)
    assert profile_token_digest(b"k" * 32, token.opaque_secret)
    assert profile_token_digest(b"k" * 32, token.raw_secret_bytes)
    response = Response()
    set_profile_cookie(response, token.cookie_value)
    clear_profile_cookie(Response())


def test_origin_non_string_and_trusted_proxy_malformed() -> None:
    assert normalize_origin(None) is None  # type: ignore[arg-type]
    assert resolve_client_ip(
        peer=None, xff="1.2.3.4", trusted_cidrs=["10.0.0.0/8"]
    ) == ("unknown")
    assert (
        resolve_client_ip(
            peer="not-an-ip",
            xff="1.2.3.4",
            trusted_cidrs=["10.0.0.0/8"],
        )
        == "unknown"
    )
    ip = resolve_client_ip(
        peer="10.0.0.1",
        xff="",
        trusted_cidrs=["", "not-a-cidr", "10.0.0.0/8"],
    )
    assert ip == "10.0.0.1"
    mapped = resolve_client_ip(
        peer="[::1]",
        xff=None,
        trusted_cidrs=["::1/128"],
    )
    assert mapped in {"::1", "unknown"}
    ported = resolve_client_ip(
        peer="10.0.0.1:8080",
        xff=None,
        trusted_cidrs=["10.0.0.0/8"],
    )
    assert ported == "10.0.0.1"
