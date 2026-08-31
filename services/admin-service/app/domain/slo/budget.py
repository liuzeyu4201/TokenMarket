"""SLO availability and error-budget freeze."""

from __future__ import annotations

from dataclasses import dataclass

WINDOW_SECONDS = 30 * 24 * 3600
TARGETS = {"dataplane": 0.999, "admin": 0.995}
FREEZE_RATIO = 0.20


@dataclass
class SLOSnapshot:
    plane: str
    target: float
    window_seconds: int
    good: int
    total: int
    availability: float
    error_budget: float
    remaining_ratio: float
    freeze_release: bool

    def as_dict(self) -> dict[str, float | int | str | bool]:
        return {
            "plane": self.plane,
            "target": self.target,
            "window_seconds": self.window_seconds,
            "good": self.good,
            "total": self.total,
            "availability": self.availability,
            "error_budget": self.error_budget,
            "remaining_ratio": self.remaining_ratio,
            "freeze_release": self.freeze_release,
        }


def snapshot(*, plane: str, good: int, total: int) -> SLOSnapshot:
    target = TARGETS[plane]
    avail = 1.0 if total <= 0 else good / total
    budget = 1.0 - target
    consumed = max(0.0, 1.0 - avail)
    remaining = 0.0 if budget <= 0 else max(0.0, (budget - consumed) / budget)
    return SLOSnapshot(
        plane=plane,
        target=target,
        window_seconds=WINDOW_SECONDS,
        good=good,
        total=total,
        availability=avail,
        error_budget=budget,
        remaining_ratio=remaining,
        freeze_release=remaining < FREEZE_RATIO,
    )
