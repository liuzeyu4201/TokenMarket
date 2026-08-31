"""Foundation privacy sentinel scanner tests (004 T012).

Covers unique vocabulary, allowlist boundaries, and zero-leak assertions for
response body, non-Set-Cookie headers, and log text. Does not require DOM,
Web Storage, or BroadcastChannel (those land in later user-story layers).
"""

from __future__ import annotations

import pytest
from tests.workflow.auth_privacy_scanner import (
    AllowlistBoundary,
    AuthSentinels,
    ForbiddenSurface,
    assert_no_findings,
    default_allowlist,
    make_unique_sentinels,
    scan_log_text,
    scan_response_body,
    scan_response_headers,
    scan_text,
)


def test_make_unique_sentinels_are_distinct_per_call() -> None:
    a = make_unique_sentinels()
    b = make_unique_sentinels()
    assert a.phone != b.phone or a.session_token != b.session_token
    assert len(a.phone) == 11
    assert len(a.otp) == 6
    assert a.session_token.startswith("tm_sess_sentinel_")
    assert a.csrf_token.startswith("tm_csrf_sentinel_")
    assert a.idempotency_key.startswith("tm_idem_sentinel_")
    assert a.hmac_key.startswith("tm_hmac_sentinel_")
    assert len(set(a.all_values())) == 6


def test_default_allowlist_covers_necessary_boundaries_only() -> None:
    rules = default_allowlist()
    assert AllowlistBoundary.SET_COOKIE_WIRE in rules["session_token"]
    assert AllowlistBoundary.INPUT_VALUE in rules["phone"]
    assert AllowlistBoundary.INPUT_VALUE in rules["otp"]
    # CSRF / HMAC must not be allowlisted on wire or input value.
    assert AllowlistBoundary.SET_COOKIE_WIRE not in rules["csrf_token"]
    assert AllowlistBoundary.INPUT_VALUE not in rules["hmac_key"]


def test_response_body_fails_on_any_sentinel() -> None:
    s = make_unique_sentinels()
    body = f'{{"message":"ok","debug_phone":"{s.phone}"}}'
    findings = scan_response_body(body, s)
    assert findings
    assert findings[0].sentinel_name == "phone"
    assert findings[0].surface == ForbiddenSurface.RESPONSE_BODY
    with pytest.raises(AssertionError, match="privacy sentinel"):
        assert_no_findings(findings, context="body")


def test_response_body_clean_passes() -> None:
    s = make_unique_sentinels()
    body = '{"code":"0","message":"success","data":{"phone_masked":"*******1234"}}'
    assert_no_findings(scan_response_body(body, s))


def test_set_cookie_allows_session_token_only() -> None:
    s = make_unique_sentinels()
    headers = {
        "Set-Cookie": (
            f"__Host-tokenmarket_session={s.session_token}; Path=/; Secure; HttpOnly; SameSite=Strict"
        ),
        "Content-Type": "application/json",
        "X-Request-ID": "req-1",
    }
    assert_no_findings(scan_response_headers(headers, s))


def test_set_cookie_rejects_otp_and_csrf() -> None:
    s = make_unique_sentinels()
    findings = scan_response_headers(
        {"Set-Cookie": f"x={s.otp}; Path=/"},
        s,
    )
    assert any(f.sentinel_name == "otp" for f in findings)

    findings_csrf = scan_response_headers(
        {"Set-Cookie": f"csrf={s.csrf_token}; Path=/"},
        s,
    )
    assert any(f.sentinel_name == "csrf_token" for f in findings_csrf)


def test_non_set_cookie_header_rejects_session_and_csrf() -> None:
    s = make_unique_sentinels()
    findings = scan_response_headers(
        {
            "X-Debug-Session": s.session_token,
            "X-CSRF-Token": s.csrf_token,
        },
        s,
    )
    names = {f.sentinel_name for f in findings}
    assert "session_token" in names
    assert "csrf_token" in names


def test_log_text_rejects_phone_otp_session() -> None:
    s = make_unique_sentinels()
    log = f"auth challenge phone={s.phone} otp={s.otp} session={s.session_token}"
    findings = scan_log_text(log, s)
    assert {f.sentinel_name for f in findings} >= {"phone", "otp", "session_token"}
    with pytest.raises(AssertionError):
        assert_no_findings(findings, context="log")


def test_log_text_clean_passes() -> None:
    s = make_unique_sentinels()
    log = "auth challenge result=accepted request_id=abc phone_masked=*******8000"
    assert_no_findings(scan_log_text(log, s))


def test_in_process_assertion_boundary_suppresses_hit() -> None:
    s = make_unique_sentinels()
    # Contract tests may hold the token in memory; scanner must support allowlist.
    hits = scan_text(
        s.session_token,
        s,
        surface="in_process",
        active_boundaries=frozenset({AllowlistBoundary.IN_PROCESS_ASSERTION}),
    )
    assert hits == []


def test_metric_and_trace_surfaces_reject_hmac_key() -> None:
    s = make_unique_sentinels()
    for surface in (ForbiddenSurface.METRIC_TEXT, ForbiddenSurface.TRACE_TEXT):
        findings = scan_text(
            f"label_key={s.hmac_key}",
            s,
            surface=surface,
            active_boundaries=frozenset(),
        )
        assert findings and findings[0].sentinel_name == "hmac_key"


def test_auth_sentinels_dataclass_roundtrip() -> None:
    raw = AuthSentinels(
        phone="19912345678",
        otp="012345",
        session_token="sess",
        csrf_token="csrf",
        idempotency_key="idem",
        hmac_key="hmac",
    )
    assert raw.as_dict()["otp"] == "012345"
    assert "012345" in raw.all_values()
