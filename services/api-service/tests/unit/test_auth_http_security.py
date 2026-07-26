"""HTTP/log redaction foundation for phone-auth privacy (004 T012 / T022).

Covers header redaction (Cookie, Set-Cookie, X-CSRF-Token, Authorization) and
message redaction for OTP/phone patterns. Does not require DOM or Web Storage.
"""

from __future__ import annotations

from app.observability import redact_headers, redact_message


def test_redact_headers_redacts_authorization() -> None:
    out = redact_headers(
        {"Authorization": "Bearer super-secret-token", "X-Request-ID": "r1"}
    )
    assert out["Authorization"] == "[REDACTED]"
    assert out["X-Request-ID"] == "r1"


def test_redact_headers_redacts_cookie_and_set_cookie() -> None:
    out = redact_headers(
        {
            "Cookie": "__Host-tokenmarket_session=opaque-session-value",
            "Set-Cookie": "__Host-tokenmarket_session=opaque; Path=/; Secure; HttpOnly",
            "Content-Type": "application/json",
        }
    )
    assert out["Cookie"] == "[REDACTED]"
    assert out["Set-Cookie"] == "[REDACTED]"
    assert out["Content-Type"] == "application/json"


def test_redact_headers_redacts_csrf_case_insensitive() -> None:
    out = redact_headers(
        {
            "X-CSRF-Token": "csrf-secret-value",
            "x-csrf-token": "another-csrf",
            "Accept": "application/json",
        }
    )
    assert out["X-CSRF-Token"] == "[REDACTED]"
    assert out["x-csrf-token"] == "[REDACTED]"
    assert out["Accept"] == "application/json"


def test_redact_headers_redacts_api_key_and_secret_named() -> None:
    out = redact_headers(
        {
            "X-Api-Key": "key-value",
            "X-Provider-Secret": "provider-secret",
            "X-Password-Hint": "should-redact",
        }
    )
    assert out["X-Api-Key"] == "[REDACTED]"
    assert out["X-Provider-Secret"] == "[REDACTED]"
    assert out["X-Password-Hint"] == "[REDACTED]"


def test_redact_message_redacts_cn_mobile() -> None:
    raw = "challenge accepted for 13800138000 request_id=abc"
    redacted = redact_message(raw)
    assert "13800138000" not in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "request_id=abc" in redacted


def test_redact_message_preserves_masked_phone() -> None:
    raw = "phone_masked=*******8000 ok"
    assert redact_message(raw) == raw


def test_redact_message_redacts_labeled_otp() -> None:
    raw = "dispatch otp=123456 to provider"
    redacted = redact_message(raw)
    assert "123456" not in redacted
    assert "[REDACTED_OTP]" in redacted
    assert "otp=" in redacted


def test_redact_message_redacts_verification_code_label() -> None:
    raw = "verification_code: 654321 pending"
    redacted = redact_message(raw)
    assert "654321" not in redacted
    assert "[REDACTED_OTP]" in redacted


def test_redact_message_redacts_labeled_session_and_csrf() -> None:
    raw = "session_token=abc123csrf csrf_token=xyz789idem idempotency_key=idem-1"
    redacted = redact_message(raw)
    assert "abc123csrf" not in redacted
    assert "xyz789idem" not in redacted
    assert "idem-1" not in redacted
    assert redacted.count("[REDACTED]") >= 3


def test_redact_message_empty_and_safe() -> None:
    assert redact_message("") == ""
    assert redact_message("status=ok code=0") == "status=ok code=0"
