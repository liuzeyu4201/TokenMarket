"""Auth privacy sentinel vocabulary and allowlist scanner (004 T012/T022 foundation).

Each acceptance or unit run generates unique phone/OTP/session/CSRF (and related)
sentinel values. The scanner distinguishes necessary instantaneous boundaries
from forbidden leak surfaces:

Allowlist (necessary boundaries only):
  - wire-level ``Set-Cookie`` response header values destined for the browser
  - phone/OTP input control *value* while the user is editing (DOM surface; later layers)
  - in-process contract assertions that must never be printed to logs/evidence

Forbidden (must be zero hits):
  - response body
  - response headers other than ``Set-Cookie``
  - logs, errors, metrics, traces (text serialization)
  - later: non-input DOM, URL/history, Web Storage, BroadcastChannel, evidence

Foundation scope deliberately excludes DOM, Web Storage, and BroadcastChannel.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class AllowlistBoundary(str, Enum):
    """Surfaces where a sentinel may appear only as a necessary transient boundary."""

    SET_COOKIE_WIRE = "set_cookie_wire"
    INPUT_VALUE = "input_value"
    IN_PROCESS_ASSERTION = "in_process_assertion"


class ForbiddenSurface(str, Enum):
    """Surfaces that must never contain raw auth sentinels."""

    RESPONSE_BODY = "response_body"
    RESPONSE_HEADER = "response_header"
    LOG_TEXT = "log_text"
    ERROR_TEXT = "error_text"
    METRIC_TEXT = "metric_text"
    TRACE_TEXT = "trace_text"


# Session token may appear only on Set-Cookie wire; phone/OTP only on input value (later).
_DEFAULT_ALLOWLIST: Mapping[str, frozenset[AllowlistBoundary]] = {
    "phone": frozenset({AllowlistBoundary.INPUT_VALUE, AllowlistBoundary.IN_PROCESS_ASSERTION}),
    "otp": frozenset({AllowlistBoundary.INPUT_VALUE, AllowlistBoundary.IN_PROCESS_ASSERTION}),
    "session_token": frozenset(
        {AllowlistBoundary.SET_COOKIE_WIRE, AllowlistBoundary.IN_PROCESS_ASSERTION}
    ),
    "csrf_token": frozenset({AllowlistBoundary.IN_PROCESS_ASSERTION}),
    "idempotency_key": frozenset({AllowlistBoundary.IN_PROCESS_ASSERTION}),
    "hmac_key": frozenset({AllowlistBoundary.IN_PROCESS_ASSERTION}),
}


@dataclass(frozen=True)
class AuthSentinels:
    """Unique per-run auth secrets used for leak detection."""

    phone: str
    otp: str
    session_token: str
    csrf_token: str
    idempotency_key: str
    hmac_key: str

    def as_dict(self) -> dict[str, str]:
        return {
            "phone": self.phone,
            "otp": self.otp,
            "session_token": self.session_token,
            "csrf_token": self.csrf_token,
            "idempotency_key": self.idempotency_key,
            "hmac_key": self.hmac_key,
        }

    def all_values(self) -> tuple[str, ...]:
        return tuple(self.as_dict().values())


@dataclass(frozen=True)
class ScanFinding:
    surface: ForbiddenSurface | str
    sentinel_name: str
    sentinel_value: str
    context: str


def make_unique_sentinels(*, rng: secrets.SystemRandom | None = None) -> AuthSentinels:
    """Build a unique sentinel vocabulary for one test or acceptance run."""
    rnd = rng or secrets.SystemRandom()
    # Distinctive CN-mobile-shaped phone that will not collide with common fixtures.
    phone = f"19{rnd.randrange(10**9):09d}"
    assert len(phone) == 11
    otp = f"{rnd.randrange(10**6):06d}"
    tag = uuid.uuid4().hex
    return AuthSentinels(
        phone=phone,
        otp=otp,
        session_token=f"tm_sess_sentinel_{tag}",
        csrf_token=f"tm_csrf_sentinel_{tag}",
        idempotency_key=f"tm_idem_sentinel_{tag}",
        hmac_key=f"tm_hmac_sentinel_{tag}",
    )


def default_allowlist() -> dict[str, frozenset[AllowlistBoundary]]:
    """Return a copy of the foundation allowlist map (sentinel field → boundaries)."""
    return {k: frozenset(v) for k, v in _DEFAULT_ALLOWLIST.items()}


def _snippet(text: str, value: str, radius: int = 24) -> str:
    idx = text.find(value)
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(value) + radius)
    return text[start:end]


def scan_text(
    text: str,
    sentinels: AuthSentinels,
    *,
    surface: ForbiddenSurface | str,
    active_boundaries: frozenset[AllowlistBoundary] | None = None,
    allowlist: Mapping[str, frozenset[AllowlistBoundary]] | None = None,
) -> list[ScanFinding]:
    """Scan free-form text for sentinel leaks on a forbidden surface.

    ``active_boundaries`` lists allowlist boundaries that apply to this scan
    (e.g. empty for logs; ``{SET_COOKIE_WIRE}`` is not used for body/logs).
    A hit is suppressed only when the sentinel field's allowlist intersects
    ``active_boundaries``.
    """
    if not text:
        return []
    rules = allowlist if allowlist is not None else _DEFAULT_ALLOWLIST
    active = active_boundaries if active_boundaries is not None else frozenset()
    findings: list[ScanFinding] = []
    for name, value in sentinels.as_dict().items():
        if not value or value not in text:
            continue
        permitted = rules.get(name, frozenset())
        if active and permitted.intersection(active):
            continue
        findings.append(
            ScanFinding(
                surface=surface,
                sentinel_name=name,
                sentinel_value=value,
                context=_snippet(text, value),
            )
        )
    return findings


def scan_response_body(body: str, sentinels: AuthSentinels) -> list[ScanFinding]:
    """Response bodies never allow raw auth sentinels."""
    return scan_text(
        body,
        sentinels,
        surface=ForbiddenSurface.RESPONSE_BODY,
        active_boundaries=frozenset(),
    )


def scan_response_headers(
    headers: Mapping[str, str] | Iterable[tuple[str, str]],
    sentinels: AuthSentinels,
) -> list[ScanFinding]:
    """Scan response headers; ``Set-Cookie`` is an allowlisted wire boundary for session."""
    items: list[tuple[str, str]]
    if isinstance(headers, Mapping):
        items = list(headers.items())
    else:
        items = list(headers)

    findings: list[ScanFinding] = []
    for name, value in items:
        lower = name.lower()
        text = f"{name}: {value}"
        if lower == "set-cookie":
            # Session credential may appear only on Set-Cookie wire; others fail.
            hits = scan_text(
                text,
                sentinels,
                surface=ForbiddenSurface.RESPONSE_HEADER,
                active_boundaries=frozenset({AllowlistBoundary.SET_COOKIE_WIRE}),
            )
            findings.extend(hits)
            continue
        findings.extend(
            scan_text(
                text,
                sentinels,
                surface=ForbiddenSurface.RESPONSE_HEADER,
                active_boundaries=frozenset(),
            )
        )
    return findings


def scan_log_text(text: str, sentinels: AuthSentinels) -> list[ScanFinding]:
    """Logs / serialized telemetry must never contain raw sentinels."""
    return scan_text(
        text,
        sentinels,
        surface=ForbiddenSurface.LOG_TEXT,
        active_boundaries=frozenset(),
    )


def assert_no_findings(findings: list[ScanFinding], *, context: str = "") -> None:
    """Fail the test if any sentinel leaks were recorded."""
    if not findings:
        return
    detail = "; ".join(
        f"{f.surface}:{f.sentinel_name} in {f.context!r}" for f in findings[:8]
    )
    prefix = f"{context}: " if context else ""
    raise AssertionError(f"{prefix}privacy sentinel leak(s): {detail}")


_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_OTP_CONTEXT_RE = re.compile(
    r"(?i)\b(otp|verification[_-]?code|sms[_-]?code|auth[_-]?code)\b\s*[:=]\s*(\d{4,8})"
)


def contains_raw_phone(text: str) -> bool:
    """Heuristic used by unit tests for non-sentinel phone leakage checks."""
    return _PHONE_RE.search(text) is not None


def contains_otp_context(text: str) -> bool:
    return _OTP_CONTEXT_RE.search(text) is not None
