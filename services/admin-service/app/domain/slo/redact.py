"""Scan telemetry blobs for secrets."""

from __future__ import annotations

_MARKERS = (
    "sk-",
    "api_key",
    "apikey",
    "password",
    "otp",
    "begin private",
    "plaintext",
)


def scan_secrets(blob: str) -> list[str]:
    lowered = blob.lower()
    return [m for m in _MARKERS if m in lowered]


def redact(blob: str) -> str:
    out = blob
    for marker in scan_secrets(blob):
        out = out.replace(marker, "[redacted]")
        out = out.replace(marker.upper(), "[redacted]")
    return out
