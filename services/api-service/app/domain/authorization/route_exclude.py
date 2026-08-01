"""Pure self-route exclusion for buyer traffic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID


@dataclass(frozen=True)
class RouteCandidate:
    resource_id: UUID
    owner_user_id: UUID
    lifecycle_status: str


def exclude_self_owned_seller_keys(
    buyer_user_id: UUID,
    candidates: Sequence[RouteCandidate],
) -> tuple[list[RouteCandidate], int]:
    """Filter out self-owned and non-active candidates.

    Returns (filtered, excluded_count) where excluded_count is how many
    input items were dropped (self-owned or non-active).
    """
    filtered: list[RouteCandidate] = []
    excluded = 0
    for c in candidates:
        if c.owner_user_id == buyer_user_id or c.lifecycle_status != "active":
            excluded += 1
            continue
        filtered.append(c)
    return filtered, excluded
