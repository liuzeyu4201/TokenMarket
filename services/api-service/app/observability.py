"""Observability helpers for the API service scaffold."""

from __future__ import annotations

import logging
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


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """Remove secret-like header values before logging."""
    safe: dict[str, Any] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in ("authorization", "x-api-key") or "secret" in lower:
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe


def generate_request_id() -> str:
    """Return a new opaque request id."""
    return str(uuid.uuid4())
