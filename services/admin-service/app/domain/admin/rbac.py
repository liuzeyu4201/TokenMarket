"""Least-privilege admin RBAC matrix."""

from __future__ import annotations

from typing import FrozenSet

ROLES = frozenset({"support", "supply_ops", "pricing", "ledger", "security_audit"})

NEVER: FrozenSet[str] = frozenset(
    {"credential.read", "ledger.edit_balance", "audit.delete"}
)

HIGH_RISK: FrozenSet[str] = frozenset(
    {
        "price.publish",
        "route.rollback",
        "connection.replace_dedicated",
        "user.force_logout",
        "ledger.reverse",
        "break_glass",
    }
)

# (role, readonly) -> allowed actions
_MATRIX: dict[tuple[str, bool], FrozenSet[str]] = {
    ("support", False): frozenset({"user.lookup", "user.force_logout", "audit.read"}),
    ("support", True): frozenset({"user.lookup", "audit.read"}),
    ("supply_ops", False): frozenset(
        {"connection.view_health", "connection.replace_dedicated"}
    ),
    ("supply_ops", True): frozenset({"connection.view_health"}),
    ("pricing", False): frozenset({"price.publish", "route.rollback"}),
    ("pricing", True): frozenset(),
    ("ledger", False): frozenset({"ledger.reverse"}),
    ("ledger", True): frozenset(),
    ("security_audit", False): frozenset(
        {
            "audit.read",
            "user.force_logout",
            "user.lookup",
            "connection.view_health",
            "break_glass",
        }
    ),
    ("security_audit", True): frozenset(
        {"audit.read", "user.lookup", "connection.view_health"}
    ),
}


def evaluate(role: str, readonly: bool, action: str) -> bool:
    if action in NEVER:
        return False
    if role not in ROLES:
        return False
    allowed = _MATRIX.get((role, readonly), frozenset())
    return action in allowed
