"""Observability helpers for the Billing service scaffold."""

from __future__ import annotations

import logging
import uuid
from typing import Any


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
