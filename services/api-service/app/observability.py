"""Observability helpers for the API service scaffold."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from prometheus_client import Counter, Histogram

READINESS_PROBES_TOTAL = Counter(
    "tokenmarket_postgres_readiness_probes_total",
    "Completed postgres readiness probe attempts.",
)
READINESS_PROBE_FAILURES_TOTAL = Counter(
    "tokenmarket_postgres_readiness_probe_failures_total",
    "Postgres readiness probe attempts that were not ready.",
)
READINESS_PROBE_DURATION_SECONDS = Histogram(
    "tokenmarket_postgres_readiness_probe_duration_seconds",
    "Duration of postgres readiness probe attempts in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)


def record_readiness_probe(ok: bool, duration_seconds: float) -> None:
    """Record one completed readiness probe.

    The probe metric families are intentionally label-free so no URL,
    username, database, exception, SQL, password, or workspace value can
    ever appear in the exposition.
    """
    READINESS_PROBES_TOTAL.inc()
    if not ok:
        READINESS_PROBE_FAILURES_TOTAL.inc()
    READINESS_PROBE_DURATION_SECONDS.observe(max(duration_seconds, 0.0))


def configure_logging() -> logging.Logger:
    fmt = '{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}'
    logging.basicConfig(level=logging.INFO, format=fmt)
    return logging.getLogger("api-service")


_REDACTED_HEADER_NAMES = frozenset(
    {
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
        "x-csrf-token",
        "x-session-token",
    }
)

# Full CN mobile MSISDN (skip already-masked spans that contain *).
_PHONE_PATTERN = re.compile(r"(?<![*\d])1[3-9]\d{9}(?!\d)")
# Labeled OTP only — avoid redacting arbitrary 6-digit numbers (ports, counts).
_OTP_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(otp|verification[_-]?code|sms[_-]?code|auth[_-]?code)\b(\s*[:=]\s*)(\d{4,8})"
)
_TOKEN_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(session[_-]?token|csrf[_-]?token|idempotency[_-]?key)\b(\s*[:=]\s*)(\S+)"
)


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """Remove secret-like header values before logging (incl. Cookie/CSRF).

    Always redacts Authorization, Cookie, Set-Cookie, X-CSRF-Token, and
    X-Api-Key (case-insensitive), plus any header whose name contains
    ``secret``, ``password``, or ``token``.
    """
    safe: dict[str, Any] = {}
    for key, value in headers.items():
        lower = key.lower()
        if (
            lower in _REDACTED_HEADER_NAMES
            or "secret" in lower
            or "password" in lower
            or "token" in lower
        ):
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe


def redact_message(message: str) -> str:
    """Redact phone numbers, labeled OTP codes, and labeled auth tokens from text.

    Defense-in-depth for log lines, error messages, and trace attributes before
    serialization. Prefer never writing raw PII at the call site.
    """
    if not message:
        return message
    text = _PHONE_PATTERN.sub("[REDACTED_PHONE]", message)
    text = _OTP_CONTEXT_PATTERN.sub(r"\1\2[REDACTED_OTP]", text)
    text = _TOKEN_CONTEXT_PATTERN.sub(r"\1\2[REDACTED]", text)
    return text


def redact_text(text: str) -> str:
    """Alias for :func:`redact_message` (historical name)."""
    return redact_message(text)


def generate_request_id() -> str:
    """Return a new opaque request id."""
    return str(uuid.uuid4())


# Registration metrics — no phone / high-cardinality labels (FR ER-006)
REGISTRATION_ATTEMPTS_TOTAL = Counter(
    "tokenmarket_registration_attempts_total",
    "Registration attempts by coarse result class.",
    ["result"],
)
REGISTRATION_DURATION_SECONDS = Histogram(
    "tokenmarket_registration_duration_seconds",
    "Registration request duration in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
REGISTRATION_RATE_LIMITED_TOTAL = Counter(
    "tokenmarket_registration_rate_limited_total",
    "Registration attempts rejected by rate limit.",
)
RATE_LIMIT_BACKEND_UNAVAILABLE_TOTAL = Counter(
    "tokenmarket_rate_limit_backend_unavailable_total",
    "Rate-limit backend (Redis) unavailable on registration path.",
)


def record_registration_attempt(result: str) -> None:
    """Increment attempt counter; result is a low-cardinality class."""
    safe = result.replace(" ", "_")[:64]
    REGISTRATION_ATTEMPTS_TOTAL.labels(result=safe).inc()


def record_registration_duration(seconds: float) -> None:
    REGISTRATION_DURATION_SECONDS.observe(max(seconds, 0.0))


def record_rate_limited() -> None:
    REGISTRATION_RATE_LIMITED_TOTAL.inc()


def record_rate_limit_backend_unavailable() -> None:
    RATE_LIMIT_BACKEND_UNAVAILABLE_TOTAL.inc()


# ---------------------------------------------------------------------------
# Authentication metrics (004) — low-cardinality labels only; never phone/IP/OTP
# ---------------------------------------------------------------------------

AUTH_CHALLENGE_REQUESTS_TOTAL = Counter(
    "tokenmarket_auth_challenge_requests_total",
    "Verification challenge requests by coarse result class.",
    ["result"],
)
AUTH_CHALLENGE_DURATION_SECONDS = Histogram(
    "tokenmarket_auth_challenge_duration_seconds",
    "Challenge request duration seconds (pre-dispatch).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
AUTH_VERIFY_ATTEMPTS_TOTAL = Counter(
    "tokenmarket_auth_verify_attempts_total",
    "OTP verification attempts by coarse result class.",
    ["result"],
)
AUTH_SESSION_EVENTS_TOTAL = Counter(
    "tokenmarket_auth_session_events_total",
    "Session lifecycle events.",
    ["event"],
)
AUTH_SESSION_CHECK_DURATION_SECONDS = Histogram(
    "tokenmarket_auth_session_check_duration_seconds",
    "Session bootstrap / validation duration in seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
AUTH_SESSION_REJECTED_TOTAL = Counter(
    "tokenmarket_auth_session_rejected_total",
    "Session validation rejections by low-cardinality reason.",
    ["reason"],
)
AUTH_SESSION_REVOCATION_VISIBILITY_SECONDS = Histogram(
    "tokenmarket_auth_session_revocation_visibility_seconds",
    "Time from revoke commit until subsequent check observes rejection.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
AUTH_DISPATCHER_CLAIMS_TOTAL = Counter(
    "tokenmarket_auth_dispatcher_claims_total",
    "Dispatcher claim outcomes.",
    ["result"],
)
AUTH_DISPATCHER_QUEUE_AGE_SECONDS = Histogram(
    "tokenmarket_auth_dispatcher_queue_age_seconds",
    "Age of claimed pending delivery work when claimed.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0, 60.0, 120.0),
)
AUTH_PROVIDER_OUTCOMES_TOTAL = Counter(
    "tokenmarket_auth_provider_outcomes_total",
    "SMS provider delivery outcomes (low-cardinality category).",
    ["outcome"],
)
AUTH_RATE_LIMITED_TOTAL = Counter(
    "tokenmarket_auth_rate_limited_total",
    "Auth challenge rate-limit rejections.",
)
AUTH_CSRF_REJECTED_TOTAL = Counter(
    "tokenmarket_auth_csrf_rejected_total",
    "CSRF or Origin rejections on auth write paths.",
    ["reason"],
)
AUTH_CLEANUP_ROWS_TOTAL = Counter(
    "tokenmarket_auth_cleanup_rows_total",
    "Authentication retention cleanup rows deleted.",
    ["table"],
)

# Stable event names for structured logs / alert correlation (no PII).
AUTH_EVENT_NAMES = frozenset(
    {
        "auth.challenge.accepted",
        "auth.challenge.rate_limited",
        "auth.challenge.delivery_unavailable",
        "auth.verify.success",
        "auth.verify.failed",
        "auth.session.issued",
        "auth.session.revoked",
        "auth.session.bootstrap",
        "auth.session.rejected",
        "auth.dispatcher.claim",
        "auth.dispatcher.finalize",
        "auth.provider.outcome",
        "auth.cleanup.completed",
        "auth.csrf.rejected",
        "auth.origin.rejected",
    }
)


def record_auth_challenge(result: str, duration_seconds: float) -> None:
    safe = result.replace(" ", "_")[:64]
    AUTH_CHALLENGE_REQUESTS_TOTAL.labels(result=safe).inc()
    AUTH_CHALLENGE_DURATION_SECONDS.observe(max(duration_seconds, 0.0))


def record_auth_verify(result: str) -> None:
    AUTH_VERIFY_ATTEMPTS_TOTAL.labels(result=result.replace(" ", "_")[:64]).inc()


def record_auth_session_event(event: str) -> None:
    AUTH_SESSION_EVENTS_TOTAL.labels(event=event.replace(" ", "_")[:64]).inc()


def record_auth_session_check(duration_seconds: float) -> None:
    AUTH_SESSION_CHECK_DURATION_SECONDS.observe(max(duration_seconds, 0.0))


def record_auth_session_rejected(reason: str) -> None:
    AUTH_SESSION_REJECTED_TOTAL.labels(reason=reason.replace(" ", "_")[:64]).inc()


def record_auth_session_revocation_visibility(seconds: float) -> None:
    AUTH_SESSION_REVOCATION_VISIBILITY_SECONDS.observe(max(seconds, 0.0))


def record_auth_dispatcher_claim(
    result: str, queue_age_seconds: float | None = None
) -> None:
    AUTH_DISPATCHER_CLAIMS_TOTAL.labels(result=result.replace(" ", "_")[:64]).inc()
    if queue_age_seconds is not None:
        AUTH_DISPATCHER_QUEUE_AGE_SECONDS.observe(max(queue_age_seconds, 0.0))


def record_auth_provider_outcome(outcome: str) -> None:
    AUTH_PROVIDER_OUTCOMES_TOTAL.labels(outcome=outcome.replace(" ", "_")[:64]).inc()


def record_auth_rate_limited() -> None:
    AUTH_RATE_LIMITED_TOTAL.inc()


def record_auth_csrf_rejected(reason: str) -> None:
    AUTH_CSRF_REJECTED_TOTAL.labels(reason=reason.replace(" ", "_")[:64]).inc()


def record_auth_cleanup_rows(table: str, count: int) -> None:
    if count > 0:
        AUTH_CLEANUP_ROWS_TOTAL.labels(table=table.replace(" ", "_")[:64]).inc(count)


def emit_auth_event(logger: logging.Logger, event_name: str, **fields: Any) -> None:
    """Emit a structured auth event with request_id; never include PII fields."""
    if event_name not in AUTH_EVENT_NAMES:
        event_name = "auth.unknown"
    # Drop high-risk keys if callers pass them accidentally.
    blocked = {
        "phone",
        "otp",
        "code",
        "token",
        "csrf",
        "cookie",
        "password",
        "authorization",
    }
    safe_fields = {
        k: ("[REDACTED]" if k.lower() in blocked else v) for k, v in fields.items()
    }
    logger.info(event_name, extra=safe_fields)
