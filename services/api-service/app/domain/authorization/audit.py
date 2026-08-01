"""Audit policy: which decisions require durable events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.domain.authorization.codes import ReasonCode
from app.domain.authorization.matrix import POLICY_VERSION, Action

AUDIT_RETENTION_DAYS = 90


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def delete_after(now: datetime | None = None) -> datetime:
    base = now or utc_now()
    return base + timedelta(days=AUDIT_RETENTION_DAYS)


def requires_per_request_audit(
    *,
    allowed: bool,
    action: Action,
    is_state_change: bool,
) -> bool:
    """Return True when a durable authz security event is required."""
    if is_state_change:
        return True
    if not allowed:
        return True
    # High-frequency allow paths: no per-request authz audit.
    if action in (Action.proxy_key_use, Action.route_candidate_exclude_self):
        return False
    return False


def event_type_for(reason: ReasonCode | None, *, allowed: bool, is_state_change: bool) -> str:
    if is_state_change:
        return "authz.resource_state_change"
    if reason is None:
        return "authz.allowed"
    mapping = {
        ReasonCode.ROLE_DENIED: "authz.role_denied",
        ReasonCode.ACCOUNT_SUSPENDED: "authz.account_unavailable",
        ReasonCode.ACCOUNT_DELETED: "authz.account_unavailable",
        ReasonCode.ACCOUNT_INACTIVE: "authz.account_unavailable",
        ReasonCode.NOT_OWNER: "authz.ownership_denied",
        ReasonCode.RESOURCE_MISSING: "authz.ownership_denied",
        ReasonCode.RESOURCE_SOFT_DELETED: "authz.ownership_denied",
        ReasonCode.SELF_ROUTE_EMPTY: "authz.self_route_blocked",
        ReasonCode.UNAUTHENTICATED: "authz.unauthenticated",
    }
    return mapping.get(reason, "authz.denied")


def build_event_payload(
    *,
    action: Action | str,
    reason: ReasonCode | None,
    allowed: bool,
    is_state_change: bool,
    actor_user_id: UUID | None,
    session_id: UUID | None,
    resource_type: str | None,
    resource_id: UUID | None,
    request_id: str,
    safe_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome = "allowed_state_change" if (allowed and is_state_change) else (
        "allowed" if allowed else "denied"
    )
    return {
        "event_type": event_type_for(reason, allowed=allowed, is_state_change=is_state_change),
        "outcome": outcome if allowed else "denied",
        "reason_code": reason.value if reason else ("ALLOWED" if allowed else "DENIED"),
        "action": action.value if isinstance(action, Action) else str(action),
        "policy_version": POLICY_VERSION,
        "actor_user_id": actor_user_id,
        "session_id": session_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_id": request_id,
        "safe_metadata": safe_metadata or {},
        "delete_after": delete_after(),
    }
