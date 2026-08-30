"""Workspace lens: account role is the capability ceiling."""

from __future__ import annotations

WORKSPACES = frozenset({"buyer", "seller"})


def default_workspace(role: str) -> str:
    return "seller" if str(role) == "seller" else "buyer"


def workspace_allowed(role: str, workspace: str) -> bool:
    if workspace not in WORKSPACES:
        return False
    role_s = str(role)
    if role_s == "both":
        return True
    return role_s == workspace


def effective_role(account_role: str, workspace: str | None) -> str:
    """Return the matrix role. Unknown workspace falls back to account role."""
    role_s = str(account_role)
    if workspace is None:
        return role_s
    if not workspace_allowed(role_s, workspace):
        return ""
    if role_s == "both":
        return workspace
    return role_s
