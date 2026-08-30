"""Project status transitions."""

from __future__ import annotations

TRANSITIONS: dict[tuple[str, str], str] = {
    ("draft", "activate"): "active",
    ("draft", "archive"): "archived",
    ("active", "suspend"): "suspended",
    ("active", "archive"): "archived",
    ("suspended", "activate"): "active",
    ("suspended", "archive"): "archived",
}


def next_status(current: str, action: str) -> str | None:
    return TRANSITIONS.get((current, action))
