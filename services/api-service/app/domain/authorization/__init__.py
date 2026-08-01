"""Authorization domain: RBAC matrix, ownership, self-route exclusion, audit."""

from __future__ import annotations

from app.domain.authorization.codes import AuthzCode
from app.domain.authorization.matrix import POLICY_VERSION, Action, is_action_allowed
from app.domain.authorization.service import AuthorizationService, Decision

__all__ = [
    "Action",
    "AuthzCode",
    "AuthorizationService",
    "Decision",
    "POLICY_VERSION",
    "is_action_allowed",
]
