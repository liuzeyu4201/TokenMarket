"""Authenticated actor for seller/proxy key HTTP (session + live role)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AuthIdentityError, resolve_authenticated_identity
from app.domain.users.models import User, UserStatus
from app.errors import MSG_SERVICE_UNAVAILABLE
from app.schemas.envelope import error_envelope


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    role: str
    status: str


async def resolve_actor(request: Request) -> Actor | JSONResponse:
    override = getattr(request.app.state, "actor_override", None)
    if isinstance(override, Actor):
        return override
    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return JSONResponse(
            status_code=503,
            content=error_envelope(
                "SERVICE_UNAVAILABLE", MSG_SERVICE_UNAVAILABLE, request_id=rid
            ),
        )
    async with factory() as session:
        ident = await resolve_authenticated_identity(request, session, request_id=rid)
        if isinstance(ident, AuthIdentityError):
            return JSONResponse(
                status_code=ident.http_status,
                content=error_envelope(ident.code, ident.message, request_id=rid),
            )
        user = await _load_user(session, ident.user_id)
        if user is None or user.status != UserStatus.active:
            return JSONResponse(
                status_code=401,
                content=error_envelope("UNAUTHENTICATED", "未认证", request_id=rid),
            )
        return Actor(user_id=user.id, role=user.role.value, status=user.status.value)


async def _load_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
