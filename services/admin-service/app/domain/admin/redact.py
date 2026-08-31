"""Strip secrets from audit before/after summaries."""

from __future__ import annotations

from typing import Any

_DENIED = (
    "secret",
    "password",
    "token",
    "otp",
    "credential",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _DENIED):
                out[key] = "[redacted]"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(part in lowered for part in ("secret", "token=", "sk-")):
            return "[redacted]"
    return value
