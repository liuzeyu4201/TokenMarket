"""Bounded metric labels."""

from __future__ import annotations

ALLOWED = frozenset(
    {
        "protocol",
        "endpoint",
        "status",
        "plane",
        "stream",
        "result",
        "reason",
        "state",
    }
)

FORBIDDEN = frozenset(
    {"user_id", "project_id", "request_id", "account_id", "api_key"}
)


def allow_labels(labels: dict[str, str]) -> bool:
    for key in labels:
        if key in FORBIDDEN or key not in ALLOWED:
            return False
    return True
