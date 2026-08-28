"""Owner eligibility for proxy authentication and seller-key routing."""

from __future__ import annotations

from dataclasses import dataclass

BUYER_ROLES = frozenset({"buyer", "both"})
SELLER_ROLES = frozenset({"seller", "both"})
ACTIVE_STATUS = "active"


@dataclass(frozen=True)
class OwnerState:
    status: str
    role: str
    is_deleted: bool = False


def owner_can_use_proxy_keys(
    status: str, role: str, is_deleted: bool = False
) -> bool:
    """Active, non-deleted buyer/both owners may authenticate proxy keys."""
    return (not is_deleted) and status == ACTIVE_STATUS and role in BUYER_ROLES


def owner_can_route_seller_keys(
    status: str, role: str, is_deleted: bool = False
) -> bool:
    """Active, non-deleted seller/both owners may appear in the routable pool."""
    return (not is_deleted) and status == ACTIVE_STATUS and role in SELLER_ROLES


def owner_state_allows_proxy(owner: OwnerState | None) -> bool:
    if owner is None:
        return False
    return owner_can_use_proxy_keys(owner.status, owner.role, owner.is_deleted)


def owner_state_allows_seller(owner: OwnerState | None) -> bool:
    if owner is None:
        return False
    return owner_can_route_seller_keys(owner.status, owner.role, owner.is_deleted)
