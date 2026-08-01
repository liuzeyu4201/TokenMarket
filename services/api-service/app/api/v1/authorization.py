"""Authorization HTTP: evaluate, exclude-self, optional fixtures."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import resolve_app_mode
from app.dependencies import (
    AuthIdentity,
    AuthIdentityError,
    get_auth_settings,
    resolve_authenticated_identity,
)
from app.domain.authorization.matrix import Action
from app.domain.authorization.route_exclude import RouteCandidate
from app.domain.authorization.service import AuthorizationService, Decision
from app.errors import MSG_CSRF_INVALID, MSG_ORIGIN_REJECTED
from app.observability import record_auth_csrf_rejected
from app.repositories.authorization import AuthorizationRepository
from app.schemas.authorization import (
    EvaluateRequest,
    FixtureCreateResourceRequest,
    FixturePatchResourceRequest,
    RouteExcludeRequest,
)
from app.schemas.envelope import error_envelope, success_envelope
from app.security.csrf import verify_csrf_token
from app.security.origin import origin_allowed
from app.security.session import SESSION_COOKIE_NAME

logger = logging.getLogger("api-service")

router = APIRouter(prefix="/api/v1/authorization", tags=["authorization"])

_DEFAULT_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://127.0.0.1:5173",
    "https://localhost:5173",
]


def fixtures_enabled() -> bool:
    mode = resolve_app_mode()
    if mode not in ("local", "test"):
        return False
    raw = (os.environ.get("AUTHORIZATION_FIXTURES_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _allowed_origins(request: Request) -> list[str]:
    settings = get_auth_settings(request)
    origins = settings.browser_origin_list
    return origins if origins else list(_DEFAULT_ORIGINS)


def _identity_error_response(
    err: AuthIdentityError, request_id: str
) -> JSONResponse:
    return JSONResponse(
        status_code=err.http_status,
        content=error_envelope(err.code, err.message, request_id=request_id),
    )


async def _require_identity(
    request: Request, session: AsyncSession
) -> AuthIdentity | JSONResponse:
    rid = _request_id(request)
    result = await resolve_authenticated_identity(
        request, session, request_id=rid
    )
    if isinstance(result, AuthIdentityError):
        return _identity_error_response(result, rid)
    return result


def _csrf_origin_guard(
    request: Request,
    *,
    origin: str | None,
    csrf_presented: str | None,
    session_id: uuid.UUID | None,
) -> JSONResponse | None:
    """Enforce Origin + session-bound CSRF for fixture state-changing writes."""
    rid = _request_id(request)
    settings = get_auth_settings(request)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if origin is not None or cookie:
        if not origin_allowed(origin, _allowed_origins(request)):
            record_auth_csrf_rejected("origin")
            return JSONResponse(
                status_code=403,
                content=error_envelope(
                    "ORIGIN_REJECTED", MSG_ORIGIN_REJECTED, request_id=rid
                ),
            )
    if session_id is None:
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "CSRF_INVALID", MSG_CSRF_INVALID, request_id=rid
            ),
        )
    csrf_mat = settings.key_material("csrf")
    versions = [csrf_mat.version]
    if csrf_mat.previous is not None and csrf_mat.version > 1:
        versions.append(csrf_mat.version - 1)
    for ver in versions:
        key = csrf_mat.resolve(ver)
        if verify_csrf_token(key, ver, session_id, csrf_presented):
            return None
    record_auth_csrf_rejected("csrf")
    return JSONResponse(
        status_code=403,
        content=error_envelope("CSRF_INVALID", MSG_CSRF_INVALID, request_id=rid),
    )


def _decision_response(decision: Decision, request_id: str) -> JSONResponse:
    if decision.allowed and decision.code == "0":
        if decision.action == Action.route_candidate_exclude_self.value:
            payload = {
                "candidates": [
                    {
                        "resource_id": str(c.resource_id),
                        "owner_user_id": str(c.owner_user_id),
                        "lifecycle_status": c.lifecycle_status,
                    }
                    for c in decision.filtered_candidates
                ],
                "excluded_count": decision.excluded_count,
                "policy_version": decision.policy_version,
            }
            return JSONResponse(
                status_code=200,
                content=success_envelope(payload, request_id=request_id),
            )
        if decision.resource:
            return JSONResponse(
                status_code=200,
                content=success_envelope(decision.resource, request_id=request_id),
            )
        data: dict[str, Any] = {
            "allowed": True,
            "action": decision.action,
            "policy_version": decision.policy_version,
        }
        if decision.resource_type:
            data["resource_type"] = decision.resource_type
        if decision.resource_id:
            data["resource_id"] = str(decision.resource_id)
        return JSONResponse(
            status_code=200,
            content=success_envelope(data, request_id=request_id),
        )
    return JSONResponse(
        status_code=decision.http_status,
        content=error_envelope(
            decision.code, decision.message, request_id=request_id
        ),
    )


async def _session_from_request(request: Request) -> AsyncSession:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        from app.errors import DependencyUnavailableError

        raise DependencyUnavailableError()
    return factory()


@router.post("/evaluate")
async def evaluate_authorization(
    body: EvaluateRequest,
    request: Request,
) -> JSONResponse:
    rid = _request_id(request)
    session = await _session_from_request(request)
    async with session:
        identity = await _require_identity(request, session)
        if isinstance(identity, JSONResponse):
            return identity
        service = AuthorizationService(AuthorizationRepository(session))
        decision = await service.authorize(
            user_id=identity.user_id,
            session_id=identity.session_id,
            action=body.action,
            request_id=rid,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            client_user_id=body.user_id,
            client_role=body.role,
            apply_mutation=False,
        )
        return _decision_response(decision, rid)


@router.post("/route-candidates/exclude-self")
async def exclude_self_route_candidates(
    body: RouteExcludeRequest,
    request: Request,
) -> JSONResponse:
    rid = _request_id(request)
    session = await _session_from_request(request)
    async with session:
        identity = await _require_identity(request, session)
        if isinstance(identity, JSONResponse):
            return identity
        candidates = [
            RouteCandidate(
                resource_id=c.resource_id,
                owner_user_id=c.owner_user_id,
                lifecycle_status=c.lifecycle_status,
            )
            for c in body.candidates
        ]
        service = AuthorizationService(AuthorizationRepository(session))
        decision = await service.authorize(
            user_id=identity.user_id,
            session_id=identity.session_id,
            action=Action.route_candidate_exclude_self,
            request_id=rid,
            candidates=candidates,
            apply_mutation=False,
        )
        return _decision_response(decision, rid)


@router.post("/fixtures/resources")
async def fixture_create_resource(
    body: FixtureCreateResourceRequest,
    request: Request,
    origin: str | None = Header(default=None, alias="Origin"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> JSONResponse:
    rid = _request_id(request)
    if not fixtures_enabled():
        return JSONResponse(
            status_code=404,
            content=error_envelope("RESOURCE_NOT_FOUND", "资源不存在", request_id=rid),
        )
    session = await _session_from_request(request)
    async with session:
        identity = await _require_identity(request, session)
        if isinstance(identity, JSONResponse):
            return identity
        guard = _csrf_origin_guard(
            request,
            origin=origin,
            csrf_presented=csrf_token,
            session_id=identity.session_id,
        )
        if guard is not None:
            return guard
        service = AuthorizationService(AuthorizationRepository(session))
        decision = await service.authorize(
            user_id=identity.user_id,
            session_id=identity.session_id,
            action=body.action,
            request_id=rid,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            apply_mutation=True,
        )
        return _decision_response(decision, rid)


@router.get("/fixtures/resources/{resource_type}/{resource_id}")
async def fixture_read_resource(
    resource_type: str,
    resource_id: uuid.UUID,
    request: Request,
) -> JSONResponse:
    rid = _request_id(request)
    if not fixtures_enabled():
        return JSONResponse(
            status_code=404,
            content=error_envelope("RESOURCE_NOT_FOUND", "资源不存在", request_id=rid),
        )
    session = await _session_from_request(request)
    async with session:
        identity = await _require_identity(request, session)
        if isinstance(identity, JSONResponse):
            return identity
        service = AuthorizationService(AuthorizationRepository(session))
        decision = await service.authorize(
            user_id=identity.user_id,
            session_id=identity.session_id,
            action=(
                Action.proxy_key_use
                if resource_type == "proxy_key"
                else Action.seller_key_read
            ),
            request_id=rid,
            resource_type=resource_type,
            resource_id=resource_id,
            apply_mutation=False,
        )
        return _decision_response(decision, rid)


@router.patch("/fixtures/resources/{resource_type}/{resource_id}")
async def fixture_patch_resource(
    resource_type: str,
    resource_id: uuid.UUID,
    body: FixturePatchResourceRequest,
    request: Request,
    origin: str | None = Header(default=None, alias="Origin"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> JSONResponse:
    rid = _request_id(request)
    if not fixtures_enabled():
        return JSONResponse(
            status_code=404,
            content=error_envelope("RESOURCE_NOT_FOUND", "资源不存在", request_id=rid),
        )
    session = await _session_from_request(request)
    async with session:
        identity = await _require_identity(request, session)
        if isinstance(identity, JSONResponse):
            return identity
        guard = _csrf_origin_guard(
            request,
            origin=origin,
            csrf_presented=csrf_token,
            session_id=identity.session_id,
        )
        if guard is not None:
            return guard
        service = AuthorizationService(AuthorizationRepository(session))
        decision = await service.authorize(
            user_id=identity.user_id,
            session_id=identity.session_id,
            action=body.action,
            request_id=rid,
            resource_type=resource_type,
            resource_id=resource_id,
            apply_mutation=True,
            lifecycle_status=body.lifecycle_status,
        )
        return _decision_response(decision, rid)
