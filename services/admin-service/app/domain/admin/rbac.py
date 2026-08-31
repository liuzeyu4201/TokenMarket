"""Least-privilege admin RBAC matrix."""

from __future__ import annotations

from typing import FrozenSet

ROLES = frozenset({"support", "supply_ops", "pricing", "ledger", "security_audit"})

NEVER: FrozenSet[str] = frozenset({"credential.read", "ledger.edit_balance", "audit.delete"})

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
    ("support", False): frozenset(
        {
            "user.lookup",
            "user.force_logout",
            "audit.read",
            "project.lookup",
            "alert.read",
        }
    ),
    ("support", True): frozenset({"user.lookup", "audit.read", "project.lookup", "alert.read"}),
    ("supply_ops", False): frozenset(
        {
            "connection.view_health",
            "connection.replace_dedicated",
            "project.lookup",
            "alert.read",
        }
    ),
    ("supply_ops", True): frozenset({"connection.view_health", "project.lookup", "alert.read"}),
    ("pricing", False): frozenset(
        {
            "price.publish",
            "route.rollback",
            "price.read",
            "route.read",
            "alert.read",
        }
    ),
    ("pricing", True): frozenset({"price.read", "route.read", "alert.read"}),
    ("ledger", False): frozenset({"ledger.reverse", "ledger.read", "alert.read"}),
    ("ledger", True): frozenset({"ledger.read", "alert.read"}),
    ("security_audit", False): frozenset(
        {
            "audit.read",
            "user.force_logout",
            "user.lookup",
            "connection.view_health",
            "break_glass",
            "project.lookup",
            "alert.read",
        }
    ),
    ("security_audit", True): frozenset(
        {
            "audit.read",
            "user.lookup",
            "connection.view_health",
            "project.lookup",
            "alert.read",
        }
    ),
}


def evaluate(role: str, readonly: bool, action: str) -> bool:
    if action in NEVER:
        return False
    if role not in ROLES:
        return False
    allowed = _MATRIX.get((role, readonly), frozenset())
    return action in allowed
