"""FastAPI dependencies: DB session, rate limiter."""

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

from app.rate_limit import MemoryRateLimiter, RateLimiter


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


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
