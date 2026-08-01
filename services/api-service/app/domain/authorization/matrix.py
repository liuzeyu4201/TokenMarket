"""Default-deny role × action matrix (authz-matrix-v1)."""

from __future__ import annotations

import enum
from typing import Final

POLICY_VERSION: Final[str] = "authz-matrix-v1"


class Action(str, enum.Enum):
    proxy_key_create = "proxy_key.create"
    proxy_key_revoke = "proxy_key.revoke"
    proxy_key_use = "proxy_key.use"
    seller_key_register = "seller_key.register"
    seller_key_read = "seller_key.read"
    seller_key_update = "seller_key.update"
    seller_key_disable = "seller_key.disable"
    route_candidate_exclude_self = "route_candidate_exclude_self"


# role -> frozenset of allowed actions
_MATRIX: dict[str, frozenset[Action]] = {
    "buyer": frozenset(
        {
            Action.proxy_key_create,
            Action.proxy_key_revoke,
            Action.proxy_key_use,
            Action.route_candidate_exclude_self,
        }
    ),
    "seller": frozenset(
        {
            Action.seller_key_register,
            Action.seller_key_read,
            Action.seller_key_update,
            Action.seller_key_disable,
        }
    ),
    "both": frozenset(
        {
            Action.proxy_key_create,
            Action.proxy_key_revoke,
            Action.proxy_key_use,
            Action.seller_key_register,
            Action.seller_key_read,
            Action.seller_key_update,
            Action.seller_key_disable,
            Action.route_candidate_exclude_self,
        }
    ),
}


def is_action_allowed(role: str, action: Action | str) -> bool:
    """Return True only if the role explicitly allows the action."""
    act = Action(action) if isinstance(action, str) else action
    allowed = _MATRIX.get(role)
    if allowed is None:
        return False
    return act in allowed


def all_roles() -> tuple[str, ...]:
    return ("buyer", "seller", "both")


def all_actions() -> tuple[Action, ...]:
    return tuple(Action)
