"""FastAPI dependencies: DB session, rate limiter, client IP, auth identity."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fastapi import Request
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth_rate_limit import AuthRateLimiter, MemoryAuthRateLimiter
from app.rate_limit import MemoryRateLimiter, RateLimiter
from app.security.trusted_proxy import resolve_client_ip

if TYPE_CHECKING:
    from app.config import AuthSettings


@dataclass(frozen=True)
class AuthIdentity:
    """Authenticated caller identity for authorization (not a permission grant).

    Role/status must be re-read from the user fact store; never use session
    role_snapshot for RBAC decisions (FR-005a).
    """

    user_id: uuid.UUID
    session_id: uuid.UUID | None


@dataclass(frozen=True)
class AuthIdentityError:
    kind: Literal["unauthenticated", "service_unavailable"]
    http_status: int
    code: str
    message: str


def _async_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


def create_session_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(_async_url(database_url), pool_pre_ping=True)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        from app.errors import DependencyUnavailableError

        raise DependencyUnavailableError()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        # Fail closed: use a limiter that always raises backend unavailable
        return MemoryRateLimiter(fail=True)
    return limiter  # type: ignore[no-any-return]


def get_auth_rate_limiter(request: Request) -> AuthRateLimiter:
    """Auth challenge rolling limiter; fail closed if not configured."""
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if limiter is None:
        return MemoryAuthRateLimiter(fail=True)
    return limiter  # type: ignore[no-any-return]


def get_auth_settings(request: Request) -> AuthSettings:
    """Return process AuthSettings from app state (or load lazily)."""
    from app.config import AuthSettings, load_auth_settings

    settings = getattr(request.app.state, "auth_settings", None)
    if isinstance(settings, AuthSettings):
        return settings
    return load_auth_settings()


def client_ip(request: Request) -> str:
    """Resolve client IP via trusted-proxy CIDR policy (FR-008c).

    Untrusted peers never honor ``X-Forwarded-For``. When no CIDRs are
    configured, the socket peer is used so direct clients cannot forge
    rate-limit identity.
    """
    settings = getattr(request.app.state, "auth_settings", None)
    if settings is not None:
        trusted = settings.trusted_proxy_cidr_list
    else:
        # Lifespan not yet wired or unit context — fail closed (ignore XFF).
        trusted = []
    peer = request.client.host if request.client else None
    xff = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    return resolve_client_ip(peer, xff, trusted)


async def resolve_authenticated_identity(
    request: Request,
    session: AsyncSession,
    *,
    request_id: str,
) -> AuthIdentity | AuthIdentityError:
    """Validate SF04 session cookie and return user_id + session_id.

    Does **not** return role for authorization — callers must load current
    role/status from the users fact source.
    """
    from app.domain.authentication.session_service import SessionService
    from app.errors import MSG_SERVICE_UNAVAILABLE, MSG_UNAUTHENTICATED
    from app.repositories.authentication import AuthenticationRepository
    from app.security.session import (
        SESSION_COOKIE_NAME,
        parse_session_cookie,
        token_digest,
    )

    settings = get_auth_settings(request)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    service = SessionService(session, settings)
    result = await service.bootstrap_session(
        cookie_value=cookie, request_id=request_id
    )
    if result.kind == "service_unavailable":
        return AuthIdentityError(
            kind="service_unavailable",
            http_status=result.http_status,
            code=result.code,
            message=result.message or MSG_SERVICE_UNAVAILABLE,
        )
    if result.kind != "success" or not result.data:
        return AuthIdentityError(
            kind="unauthenticated",
            http_status=401,
            code="UNAUTHENTICATED",
            message=MSG_UNAUTHENTICATED,
        )

    user_id = uuid.UUID(str(result.data["user_id"]))
    session_id: uuid.UUID | None = None
    parsed = parse_session_cookie(cookie)
    if parsed is not None:
        key_version, opaque = parsed
        session_mat = settings.key_material("session")
        key = session_mat.resolve(key_version)
        if key is not None:
            digest = token_digest(key, opaque)
            repo = AuthenticationRepository(session)
            row = await repo.get_session_by_token_digest(
                token_key_version=key_version, token_digest=digest
            )
            if row is not None:
                session_id = row.id
    return AuthIdentity(user_id=user_id, session_id=session_id)
