"""FastAPI dependencies: DB session, rate limiter, client IP."""

from __future__ import annotations

from collections.abc import AsyncIterator

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


def get_auth_settings(request: Request) -> "AuthSettings":
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
