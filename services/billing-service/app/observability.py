"""Observability helpers for the Billing service scaffold."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from prometheus_client import Counter, Histogram

# SF02 PostgreSQL readiness probe instruments. They intentionally carry no
# labels: no URL, username, database, exception, SQL, password, workspace, or
# other unbounded value may ever become a label.
POSTGRES_READINESS_PROBES_TOTAL = Counter(
    "tokenmarket_postgres_readiness_probes_total",
    "Total Billing Service PostgreSQL readiness probe attempts.",
)
POSTGRES_READINESS_PROBE_FAILURES_TOTAL = Counter(
    "tokenmarket_postgres_readiness_probe_failures_total",
    "Total failed Billing Service PostgreSQL readiness probes.",
)
POSTGRES_READINESS_PROBE_DURATION_SECONDS = Histogram(
    "tokenmarket_postgres_readiness_probe_duration_seconds",
    "Billing Service PostgreSQL readiness probe duration in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)


def record_postgres_readiness_probe(ok: bool, duration_seconds: float) -> None:
    """Record one completed probe attempt, including failures."""
    POSTGRES_READINESS_PROBES_TOTAL.inc()
    if not ok:
        POSTGRES_READINESS_PROBE_FAILURES_TOTAL.inc()
    POSTGRES_READINESS_PROBE_DURATION_SECONDS.observe(duration_seconds)


def configure_logging() -> logging.Logger:
    fmt = '{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}'
    logging.basicConfig(level=logging.INFO, format=fmt)
    return logging.getLogger("billing-service")


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in ("authorization", "x-api-key") or "secret" in lower:
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe


def generate_request_id() -> str:
    return str(uuid.uuid4())
