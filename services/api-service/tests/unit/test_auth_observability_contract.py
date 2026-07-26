"""Authentication observability contract: stable names, redaction, no PII labels (004 T016)."""

from __future__ import annotations

import logging

from app.observability import (
    AUTH_EVENT_NAMES,
    emit_auth_event,
    record_auth_challenge,
    record_auth_csrf_rejected,
    record_auth_dispatcher_claim,
    record_auth_provider_outcome,
    record_auth_session_event,
    record_auth_verify,
    redact_headers,
    redact_text,
)


def test_auth_event_names_are_stable_and_low_cardinality() -> None:
    required = {
        "auth.challenge.accepted",
        "auth.verify.success",
        "auth.session.issued",
        "auth.session.revoked",
        "auth.dispatcher.claim",
        "auth.provider.outcome",
        "auth.csrf.rejected",
    }
    assert required <= AUTH_EVENT_NAMES
    for name in AUTH_EVENT_NAMES:
        assert name.startswith("auth.")
        assert " " not in name


def test_metric_recorders_accept_low_cardinality_labels() -> None:
    record_auth_challenge("accepted", 0.01)
    record_auth_verify("success")
    record_auth_session_event("issued")
    record_auth_dispatcher_claim("claimed", queue_age_seconds=0.2)
    record_auth_provider_outcome("accepted")
    record_auth_csrf_rejected("origin")


def test_redact_headers_strips_cookie_and_csrf() -> None:
    redacted = redact_headers(
        {
            "Cookie": "a=b",
            "Set-Cookie": "__Host-tokenmarket_session=secret",
            "X-CSRF-Token": "csrf-value",
            "X-Request-ID": "req-1",
            "Content-Type": "application/json",
        }
    )
    assert redacted["Cookie"] == "[REDACTED]"
    assert redacted["Set-Cookie"] == "[REDACTED]"
    assert redacted["X-CSRF-Token"] == "[REDACTED]"
    assert redacted["X-Request-ID"] == "req-1"
    assert redacted["Content-Type"] == "application/json"


def test_redact_text_masks_phone_and_otp_like_spans() -> None:
    text = "phone 13800138000 otp: 012345"
    out = redact_text(text)
    assert "13800138000" not in out
    assert "012345" not in out


def test_emit_auth_event_redacts_blocked_fields(
    caplog: logging.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("api-service-test-auth-obs")
    with caplog.at_level(logging.INFO, logger="api-service-test-auth-obs"):
        emit_auth_event(
            logger,
            "auth.challenge.accepted",
            request_id="r1",
            phone="13800138000",
            challenge_ref="c1",
        )
    # phone key must not leak raw value via message path; extra is not always in caplog
    assert "13800138000" not in caplog.text
