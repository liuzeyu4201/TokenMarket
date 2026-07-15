"""Observability helpers for the API service scaffold."""

from __future__ import annotations

import logging
import uuid
from typing import Any


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
