"""AuthorizationService: matrix, ownership, self-route, audit-before-deny."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.domain.authorization.audit import (
    build_event_payload,
    requires_per_request_audit,
)
from app.domain.authorization.codes import (
    AuthzCode,
    ReasonCode,
    public_outcome,
)
from app.domain.authorization.matrix import (
    POLICY_VERSION,
    Action,
    is_action_allowed,
)
from app.domain.authorization.route_exclude import (
    RouteCandidate,
    exclude_self_owned_seller_keys,
)
from app.domain.users.models import User, UserStatus
from app.observability import record_authz_audit_failure, record_authz_decision
from app.repositories.authorization import AuthorizationRepository

logger = logging.getLogger("api-service")

_CREATE_ACTIONS = frozenset({Action.proxy_key_create, Action.seller_key_register})
_STATE_CHANGE_ACTIONS = frozenset(
    {
        Action.proxy_key_create,
        Action.proxy_key_revoke,
        Action.seller_key_register,
        Action.seller_key_update,
        Action.seller_key_disable,
    }
)
_RESOURCE_TYPE = {
    Action.proxy_key_create: "proxy_key",
    Action.proxy_key_revoke: "proxy_key",
    Action.proxy_key_use: "proxy_key",
    Action.seller_key_register: "seller_key",
    Action.seller_key_read: "seller_key",
    Action.seller_key_update: "seller_key",
    Action.seller_key_disable: "seller_key",
}


@dataclass
class Decision:
    allowed: bool
    http_status: int
    code: str
    message: str
    reason_code: str | None = None
    policy_version: str = POLICY_VERSION
    action: str | None = None
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    filtered_candidates: list[RouteCandidate] = field(default_factory=list)
    excluded_count: int = 0
    resource: dict[str, Any] | None = None


class AuthorizationService:
    def __init__(self, repo: AuthorizationRepository) -> None:
        self._repo = repo

    async def authorize(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        action: Action | str,
        request_id: str,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        candidates: Sequence[RouteCandidate] | None = None,
        # Ignored identity fields (must not affect decision)
        client_user_id: uuid.UUID | None = None,  # noqa: ARG002
        client_role: str | None = None,  # noqa: ARG002
        apply_mutation: bool = False,
        lifecycle_status: str | None = None,
    ) -> Decision:
        """Evaluate authorization; optionally apply ownership mutation for fixtures."""
        start = time.monotonic()
        try:
            act = Action(action) if isinstance(action, str) else action
        except ValueError:
            return self._finish(
                Decision(
                    allowed=False,
                    http_status=400,
                    code=AuthzCode.VALIDATION_ERROR.value,
                    message=public_outcome(ReasonCode.VALIDATION).message,
                    reason_code=ReasonCode.VALIDATION.value,
                    action=str(action),
                ),
                start=start,
            )

        try:
            user = await self._repo.get_user(user_id)
        except (OperationalError, SQLAlchemyError):
            logger.exception("authz user load failed", extra={"request_id": request_id})
            return await self._denied(
                reason=ReasonCode.FACT_STORE_UNAVAILABLE,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                require_audit=False,
            )

        if user is None:
            return await self._denied(
                reason=ReasonCode.ACCOUNT_INACTIVE,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
            )

        eligible_reason = _account_reason(user)
        if eligible_reason is not None:
            return await self._denied(
                reason=eligible_reason,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
            )

        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if not is_action_allowed(role, act):
            return await self._denied(
                reason=ReasonCode.ROLE_DENIED,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                resource_type=resource_type or _RESOURCE_TYPE.get(act),
                resource_id=resource_id,
            )

        if act is Action.route_candidate_exclude_self:
            return await self._authorize_route(
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                candidates=candidates or (),
                start=start,
            )

        rtype = resource_type or _RESOURCE_TYPE.get(act)
        if act in _CREATE_ACTIONS:
            if not apply_mutation:
                # Pure evaluate: role already passed.
                return await self._allowed(
                    action=act,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    start=start,
                    resource_type=rtype,
                    is_state_change=False,
                )
            try:
                row = await self._repo.create_ownership(
                    resource_type=rtype or "proxy_key",
                    resource_id=resource_id,
                    owner_user_id=user_id,
                    request_id=request_id,
                )
                decision = Decision(
                    allowed=True,
                    http_status=200,
                    code=AuthzCode.OK.value,
                    message="success",
                    policy_version=POLICY_VERSION,
                    action=act.value,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    resource=_resource_view(row),
                )
                return await self._finalize_allowed(
                    decision,
                    action=act,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    start=start,
                    is_state_change=True,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                )
            except (OperationalError, SQLAlchemyError):
                logger.exception(
                    "authz create failed", extra={"request_id": request_id}
                )
                await self._repo.rollback()
                return await self._denied(
                    reason=ReasonCode.FACT_STORE_UNAVAILABLE,
                    action=act,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    start=start,
                    require_audit=False,
                )

        # Resource-bound actions
        if rtype is None or resource_id is None:
            return self._finish(
                Decision(
                    allowed=False,
                    http_status=400,
                    code=AuthzCode.VALIDATION_ERROR.value,
                    message=public_outcome(ReasonCode.VALIDATION).message,
                    reason_code=ReasonCode.VALIDATION.value,
                    action=act.value,
                ),
                start=start,
            )

        try:
            row = await self._repo.get_ownership(
                rtype, resource_id
            )  # type: ignore[assignment]
        except (OperationalError, SQLAlchemyError):
            logger.exception(
                "authz ownership load failed", extra={"request_id": request_id}
            )
            return await self._denied(
                reason=ReasonCode.FACT_STORE_UNAVAILABLE,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                require_audit=False,
            )

        own_reason = _ownership_reason(row, user_id)
        if own_reason is not None:
            return await self._denied(
                reason=own_reason,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                resource_type=rtype,
                resource_id=resource_id,
            )

        assert row is not None
        if act is Action.proxy_key_use and row.lifecycle_status != "active":
            return await self._denied(
                reason=ReasonCode.RESOURCE_MISSING,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                resource_type=rtype,
                resource_id=resource_id,
            )

        if apply_mutation and act in (
            Action.proxy_key_revoke,
            Action.seller_key_disable,
            Action.seller_key_update,
        ):
            new_status = lifecycle_status
            if act is Action.proxy_key_revoke:
                new_status = "disabled"
            elif act is Action.seller_key_disable:
                new_status = lifecycle_status or "disabled"
            if new_status is None:
                new_status = row.lifecycle_status
            try:
                row = await self._repo.update_ownership_status(
                    row, lifecycle_status=new_status
                )
            except (OperationalError, SQLAlchemyError):
                logger.exception(
                    "authz update failed", extra={"request_id": request_id}
                )
                await self._repo.rollback()
                return await self._denied(
                    reason=ReasonCode.FACT_STORE_UNAVAILABLE,
                    action=act,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    start=start,
                    require_audit=False,
                )
            decision = Decision(
                allowed=True,
                http_status=200,
                code=AuthzCode.OK.value,
                message="success",
                policy_version=POLICY_VERSION,
                action=act.value,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                resource=_resource_view(row),
            )
            return await self._finalize_allowed(
                decision,
                action=act,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                is_state_change=True,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
            )

        decision = Decision(
            allowed=True,
            http_status=200,
            code=AuthzCode.OK.value,
            message="success",
            policy_version=POLICY_VERSION,
            action=act.value,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            resource=_resource_view(row),
        )
        return await self._finalize_allowed(
            decision,
            action=act,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            start=start,
            is_state_change=False,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
        )

    async def _authorize_route(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        request_id: str,
        candidates: Sequence[RouteCandidate],
        start: float,
    ) -> Decision:
        filtered, excluded = exclude_self_owned_seller_keys(user_id, candidates)
        if not filtered:
            return await self._denied(
                reason=ReasonCode.SELF_ROUTE_EMPTY,
                action=Action.route_candidate_exclude_self,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                start=start,
                safe_metadata={
                    "input_count": len(list(candidates)),
                    "excluded_count": excluded,
                },
            )
        decision = Decision(
            allowed=True,
            http_status=200,
            code=AuthzCode.OK.value,
            message="success",
            policy_version=POLICY_VERSION,
            action=Action.route_candidate_exclude_self.value,
            filtered_candidates=list(filtered),
            excluded_count=excluded,
        )
        return await self._finalize_allowed(
            decision,
            action=Action.route_candidate_exclude_self,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            start=start,
            is_state_change=False,
            safe_metadata={
                "input_count": len(list(candidates)),
                "excluded_count": excluded,
                "output_count": len(filtered),
            },
        )

    async def _allowed(
        self,
        *,
        action: Action,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        request_id: str,
        start: float,
        resource_type: str | None,
        is_state_change: bool,
    ) -> Decision:
        decision = Decision(
            allowed=True,
            http_status=200,
            code=AuthzCode.OK.value,
            message="success",
            policy_version=POLICY_VERSION,
            action=action.value,
            resource_type=resource_type,
        )
        return await self._finalize_allowed(
            decision,
            action=action,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            start=start,
            is_state_change=is_state_change,
            resource_type=resource_type,
        )

    async def _finalize_allowed(
        self,
        decision: Decision,
        *,
        action: Action,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        request_id: str,
        start: float,
        is_state_change: bool,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        safe_metadata: dict[str, Any] | None = None,
    ) -> Decision:
        need_audit = requires_per_request_audit(
            allowed=True, action=action, is_state_change=is_state_change
        )
        if need_audit:
            ok = await self._persist_audit(
                action=action,
                reason=None,
                allowed=True,
                is_state_change=is_state_change,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                resource_type=resource_type,
                resource_id=resource_id,
                safe_metadata=safe_metadata,
            )
            if not ok:
                await self._repo.rollback()
                return self._finish(
                    Decision(
                        allowed=False,
                        http_status=503,
                        code=AuthzCode.SERVICE_UNAVAILABLE.value,
                        message=public_outcome(ReasonCode.AUDIT_PERSIST_FAILED).message,
                        reason_code=ReasonCode.AUDIT_PERSIST_FAILED.value,
                        action=action.value,
                    ),
                    start=start,
                )
            try:
                await self._repo.commit()
            except (OperationalError, SQLAlchemyError):
                await self._repo.rollback()
                return self._finish(
                    Decision(
                        allowed=False,
                        http_status=503,
                        code=AuthzCode.SERVICE_UNAVAILABLE.value,
                        message=public_outcome(
                            ReasonCode.FACT_STORE_UNAVAILABLE
                        ).message,
                        reason_code=ReasonCode.FACT_STORE_UNAVAILABLE.value,
                        action=action.value,
                    ),
                    start=start,
                )
        else:
            # No audit: commit mutations if any were flushed
            try:
                await self._repo.commit()
            except (OperationalError, SQLAlchemyError):
                await self._repo.rollback()
                return self._finish(
                    Decision(
                        allowed=False,
                        http_status=503,
                        code=AuthzCode.SERVICE_UNAVAILABLE.value,
                        message=public_outcome(
                            ReasonCode.FACT_STORE_UNAVAILABLE
                        ).message,
                        reason_code=ReasonCode.FACT_STORE_UNAVAILABLE.value,
                        action=action.value,
                    ),
                    start=start,
                )
        return self._finish(decision, start=start)

    async def _denied(
        self,
        *,
        reason: ReasonCode,
        action: Action,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        request_id: str,
        start: float,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        safe_metadata: dict[str, Any] | None = None,
        require_audit: bool = True,
    ) -> Decision:
        pub = public_outcome(reason)
        decision = Decision(
            allowed=False,
            http_status=pub.http_status,
            code=pub.code.value,
            message=pub.message,
            reason_code=reason.value,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if not require_audit:
            return self._finish(decision, start=start)

        ok = await self._persist_audit(
            action=action,
            reason=reason,
            allowed=False,
            is_state_change=False,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            resource_type=resource_type,
            resource_id=resource_id,
            safe_metadata=safe_metadata,
        )
        if not ok:
            await self._repo.rollback()
            return self._finish(
                Decision(
                    allowed=False,
                    http_status=503,
                    code=AuthzCode.SERVICE_UNAVAILABLE.value,
                    message=public_outcome(ReasonCode.AUDIT_PERSIST_FAILED).message,
                    reason_code=ReasonCode.AUDIT_PERSIST_FAILED.value,
                    action=action.value,
                ),
                start=start,
            )
        try:
            await self._repo.commit()
        except (OperationalError, SQLAlchemyError):
            await self._repo.rollback()
            return self._finish(
                Decision(
                    allowed=False,
                    http_status=503,
                    code=AuthzCode.SERVICE_UNAVAILABLE.value,
                    message=public_outcome(ReasonCode.FACT_STORE_UNAVAILABLE).message,
                    reason_code=ReasonCode.FACT_STORE_UNAVAILABLE.value,
                    action=action.value,
                ),
                start=start,
            )
        return self._finish(decision, start=start)

    async def _persist_audit(
        self,
        *,
        action: Action,
        reason: ReasonCode | None,
        allowed: bool,
        is_state_change: bool,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        request_id: str,
        resource_type: str | None,
        resource_id: uuid.UUID | None,
        safe_metadata: dict[str, Any] | None,
    ) -> bool:
        payload = build_event_payload(
            action=action,
            reason=reason,
            allowed=allowed,
            is_state_change=is_state_change,
            actor_user_id=user_id,
            session_id=session_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            safe_metadata=safe_metadata,
        )
        try:
            await self._repo.insert_security_event(payload)
            return True
        except (OperationalError, SQLAlchemyError):
            logger.exception(
                "authz audit persist failed", extra={"request_id": request_id}
            )
            record_authz_audit_failure()
            return False

    def _finish(self, decision: Decision, *, start: float) -> Decision:
        duration = time.monotonic() - start
        record_authz_decision(
            action=decision.action or "unknown",
            result="allow" if decision.allowed else "deny",
            reason=decision.reason_code or ("OK" if decision.allowed else "DENIED"),
            duration_seconds=duration,
        )
        return decision


def _account_reason(user: User) -> ReasonCode | None:
    if getattr(user, "is_deleted", False):
        return ReasonCode.ACCOUNT_DELETED
    status = user.status
    status_val = status.value if hasattr(status, "value") else str(status)
    if status_val == UserStatus.suspended.value or status_val == "suspended":
        return ReasonCode.ACCOUNT_SUSPENDED
    if status_val != UserStatus.active.value and status_val != "active":
        return ReasonCode.ACCOUNT_INACTIVE
    return None


def _ownership_reason(row: Any, user_id: uuid.UUID) -> ReasonCode | None:
    if row is None:
        return ReasonCode.RESOURCE_MISSING
    if row.lifecycle_status == "soft_deleted":
        return ReasonCode.RESOURCE_SOFT_DELETED
    if row.owner_user_id != user_id:
        return ReasonCode.NOT_OWNER
    return None


def _resource_view(row: Any) -> dict[str, Any]:
    return {
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id),
        "owner_user_id": str(row.owner_user_id),
        "lifecycle_status": row.lifecycle_status,
        "version": row.version,
    }
