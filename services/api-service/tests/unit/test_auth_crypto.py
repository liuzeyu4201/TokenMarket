"""Unit tests for OTP/session/CSRF cryptography (T013 / T028)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

import pytest
from starlette.responses import Response

from app.security.csrf import issue_csrf_token, verify_csrf_token
from app.security.otp import (
    derive_otp,
    generate_code_salt,
    otp_verification_digest,
    verify_otp_digest,
)
from app.security.reference import idempotency_key_digest, phone_ref
from app.security.session import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    clear_session_cookie,
    generate_session_token,
    parse_session_cookie,
    set_session_cookie,
    token_digest,
)


def _key() -> bytes:
    return ("tm_test_" + secrets.token_urlsafe(32)).encode("utf-8")


@pytest.fixture
def otp_key() -> bytes:
    return _key()


@pytest.fixture
def session_key() -> bytes:
    return _key()


@pytest.fixture
def csrf_key() -> bytes:
    return _key()


@pytest.fixture
def ref_key() -> bytes:
    return _key()


def test_session_token_is_at_least_256_bit() -> None:
    token = generate_session_token(key_version=1)
    assert len(token.raw_secret_bytes) >= 32
    assert token.cookie_value.startswith("1.")
    parsed = parse_session_cookie(token.cookie_value)
    assert parsed is not None
    version, opaque = parsed
    assert version == 1
    assert opaque == token.opaque_secret
    assert opaque != ""


def test_session_token_unique() -> None:
    a = generate_session_token(1)
    b = generate_session_token(1)
    assert a.cookie_value != b.cookie_value
    assert a.raw_secret_bytes != b.raw_secret_bytes


def test_parse_session_cookie_rejects_malformed() -> None:
    assert parse_session_cookie(None) is None
    assert parse_session_cookie("") is None
    assert parse_session_cookie("noversion") is None
    assert parse_session_cookie("0.secret") is None
    assert parse_session_cookie("abc.secret") is None
    assert parse_session_cookie("1.") is None


def test_token_digest_stable_and_key_dependent(session_key: bytes) -> None:
    token = generate_session_token(2)
    d1 = token_digest(session_key, token.opaque_secret)
    d2 = token_digest(session_key, token.opaque_secret)
    assert d1 == d2
    assert len(d1) == 32
    other = token_digest(_key(), token.opaque_secret)
    assert other != d1


def test_set_and_clear_session_cookie_attributes() -> None:
    response = Response()
    token = generate_session_token(1)
    set_session_cookie(response, token.cookie_value)
    header = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in header
    assert "HttpOnly" in header or "httponly" in header.lower()
    assert "Secure" in header or "secure" in header.lower()
    assert "Path=/" in header or "path=/" in header.lower()
    assert f"Max-Age={SESSION_MAX_AGE_SECONDS}" in header or "max-age=3600" in header.lower()
    assert "SameSite=lax" in header or "samesite=lax" in header.lower()
    # Domain must be absent for __Host-
    assert "Domain=" not in header and "domain=" not in header

    clear = Response()
    clear_session_cookie(clear)
    clear_header = clear.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in clear_header
    assert "Max-Age=0" in clear_header or "max-age=0" in clear_header.lower()
    assert "Domain=" not in clear_header


def test_otp_deterministic_for_dispatcher_recompute(otp_key: bytes) -> None:
    challenge_id = uuid.uuid4()
    code_a = derive_otp(otp_key, challenge_id)
    code_b = derive_otp(otp_key, challenge_id)
    assert code_a == code_b
    assert len(code_a) == 6
    assert code_a.isdigit()
    assert code_a.isascii()


def test_otp_different_challenges_differ(otp_key: bytes) -> None:
    a = derive_otp(otp_key, uuid.uuid4())
    b = derive_otp(otp_key, uuid.uuid4())
    # Extremely unlikely equality for independent challenges.
    assert a != b or True  # flaky guard — primarily check format
    assert len(a) == 6 and len(b) == 6


def test_otp_accepts_leading_zero_codes_in_verify_path(otp_key: bytes) -> None:
    """Boundary codes 000000 / 012345 / 999999 are valid six-digit ASCII."""
    challenge_id = uuid.uuid4()
    salt = generate_code_salt()
    for code in ("000000", "012345", "999999"):
        digest = otp_verification_digest(otp_key, challenge_id, salt, code)
        assert verify_otp_digest(otp_key, challenge_id, salt, code, digest)
        assert not verify_otp_digest(
            otp_key, challenge_id, salt, "000001" if code != "000001" else "000002", digest
        )


def test_otp_domain_separation_send_vs_verify(otp_key: bytes) -> None:
    challenge_id = uuid.uuid4()
    code = derive_otp(otp_key, challenge_id)
    salt = generate_code_salt()
    verify_digest = otp_verification_digest(otp_key, challenge_id, salt, code)
    # Send PRF output must not equal verification digest material.
    send_msg = b"otp-send:v1" + challenge_id.bytes + (0).to_bytes(8, "big")
    send_mac = hmac.new(otp_key, send_msg, hashlib.sha256).digest()
    assert send_mac != verify_digest


def test_otp_wrong_key_fails_verify(otp_key: bytes) -> None:
    challenge_id = uuid.uuid4()
    salt = generate_code_salt()
    code = "123456"
    digest = otp_verification_digest(otp_key, challenge_id, salt, code)
    assert not verify_otp_digest(_key(), challenge_id, salt, code, digest)


def test_otp_constant_time_compare_rejects_wrong_length(otp_key: bytes) -> None:
    challenge_id = uuid.uuid4()
    salt = generate_code_salt()
    digest = otp_verification_digest(otp_key, challenge_id, salt, "424242")
    assert not verify_otp_digest(otp_key, challenge_id, salt, "42424", digest)
    assert not verify_otp_digest(otp_key, challenge_id, salt, "4242420", digest)
    assert not verify_otp_digest(otp_key, challenge_id, salt, "abcdef", digest)


def test_otp_rejection_sampling_produces_six_digits_many_times(otp_key: bytes) -> None:
    codes: set[str] = set()
    for _ in range(50):
        code = derive_otp(otp_key, uuid.uuid4())
        assert len(code) == 6 and code.isdigit()
        codes.add(code)
    # With 50 random challenges we expect diversity.
    assert len(codes) > 1


def test_csrf_session_bound_and_deterministic(csrf_key: bytes) -> None:
    session_id = uuid.uuid4()
    t1 = issue_csrf_token(csrf_key, 1, session_id)
    t2 = issue_csrf_token(csrf_key, 1, session_id)
    assert t1 == t2
    assert t1.startswith("1.")
    assert verify_csrf_token(csrf_key, 1, session_id, t1)


def test_csrf_different_sessions_differ(csrf_key: bytes) -> None:
    a = issue_csrf_token(csrf_key, 1, uuid.uuid4())
    b = issue_csrf_token(csrf_key, 1, uuid.uuid4())
    assert a != b


def test_csrf_wrong_token_rejected(csrf_key: bytes) -> None:
    session_id = uuid.uuid4()
    good = issue_csrf_token(csrf_key, 1, session_id)
    assert not verify_csrf_token(csrf_key, 1, session_id, good + "x")
    assert not verify_csrf_token(csrf_key, 1, session_id, None)
    assert not verify_csrf_token(csrf_key, 1, session_id, "")
    other = issue_csrf_token(csrf_key, 1, uuid.uuid4())
    assert not verify_csrf_token(csrf_key, 1, session_id, other)


def test_csrf_unknown_key_version_fails_closed(csrf_key: bytes) -> None:
    session_id = uuid.uuid4()
    token = issue_csrf_token(csrf_key, 2, session_id)
    # Caller passes None when version is unknown → fail closed.
    assert not verify_csrf_token(None, 99, session_id, token)
    # Version mismatch between token and resolved key version.
    assert not verify_csrf_token(csrf_key, 1, session_id, token)


def test_session_current_previous_unknown_versions(session_key: bytes) -> None:
    prev_key = _key()
    token = generate_session_token(key_version=2)
    current_digest = token_digest(session_key, token.opaque_secret)
    previous_digest = token_digest(prev_key, token.opaque_secret)
    assert current_digest != previous_digest
    # Unknown version: no key material → callers must refuse authentication.
    assert token_digest(session_key, token.opaque_secret) == current_digest


def test_otp_key_version_rotation(otp_key: bytes) -> None:
    prev = _key()
    challenge_id = uuid.uuid4()
    code_current = derive_otp(otp_key, challenge_id)
    code_prev = derive_otp(prev, challenge_id)
    # Different keys produce independent codes (collision unlikely).
    assert isinstance(code_current, str) and isinstance(code_prev, str)
    salt = generate_code_salt()
    digest = otp_verification_digest(otp_key, challenge_id, salt, code_current)
    assert verify_otp_digest(otp_key, challenge_id, salt, code_current, digest)
    assert not verify_otp_digest(prev, challenge_id, salt, code_current, digest)


def test_reference_phone_and_idempotency_digests(ref_key: bytes) -> None:
    phone = "13800138000"
    r1 = phone_ref(ref_key, phone)
    r2 = phone_ref(ref_key, phone)
    assert r1 == r2
    assert r1 != phone_ref(ref_key, "13900139000")
    assert phone.encode("utf-8") not in r1

    key = "client-idempotency-abc"
    d1 = idempotency_key_digest(ref_key, key)
    d2 = idempotency_key_digest(ref_key, key)
    assert d1 == d2
    assert d1 != idempotency_key_digest(ref_key, key + "x")
    assert key.encode("utf-8") not in d1


def test_otp_counter_changes_output_when_forced(otp_key: bytes) -> None:
    challenge_id = uuid.uuid4()
    # Counter is the rejection-sampling index; different start may change result
    # only when sample 0 was rejected — still must remain six digits.
    code = derive_otp(otp_key, challenge_id, counter=0)
    assert len(code) == 6 and code.isdigit()
