"""API Service owned PostgreSQL readiness probe (SF02).

The service owns a lifespan-scoped async SQLAlchemy engine that maps the
operator-provided ``DATABASE_URL`` onto the locked asyncpg driver without
changing the authentication, host, or database facts. The readiness probe
executes exactly one bounded ``SELECT 1`` per attempt with no retries, and
every failure maps to a stable, secret-free category. Raw URLs, usernames,
passwords, SQL, driver messages, and exception bodies never leave this
module; they are not part of results, categories, or raised errors.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg  # type: ignore[import-untyped]  # locked driver ships no stubs
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PROBE_TIMEOUT_SECONDS = 2.0

_SYNC_DRIVERNAME = "postgresql"
_ASYNC_DRIVERNAME = "postgresql+asyncpg"


class ProbeErrorCategory(enum.Enum):
    """Stable, secret-free failure categories for the readiness probe."""

    INVALID_CONFIG = "invalid-config"
    AUTH = "auth"
    QUERY = "query"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class InvalidConfigError(ValueError):
    """DATABASE_URL is malformed or uses an unsupported driver.

    The message deliberately never includes the URL or any of its parts.
    """


@dataclass(frozen=True)
class ProbeResult:
    """Secret-free outcome of one readiness probe attempt."""

    ok: bool
    category: ProbeErrorCategory | None = None

    @classmethod
    def success(cls) -> "ProbeResult":
        return cls(ok=True)

    @classmethod
    def failure(cls, category: ProbeErrorCategory) -> "ProbeResult":
        return cls(ok=False, category=category)


ProbeCallable = Callable[[], Awaitable[ProbeResult]]


def _engine_url(database_url: str) -> URL:
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise InvalidConfigError(
            "DATABASE_URL is malformed or uses an unsupported driver"
        ) from None
    if url.drivername == _SYNC_DRIVERNAME:
        return url.set(drivername=_ASYNC_DRIVERNAME)
    if url.drivername == _ASYNC_DRIVERNAME:
        return url
    raise InvalidConfigError("DATABASE_URL is malformed or uses an unsupported driver")


def create_readiness_engine(database_url: str) -> AsyncEngine:
    """Create the lifespan-owned async engine for the readiness probe.

    Maps ``postgresql://`` onto the asyncpg driver and rejects non-async,
    unsupported drivers and malformed URLs with :class:`InvalidConfigError`.
    ``pool_pre_ping`` keeps pooled connections honest across dependency
    restarts. The engine is lazy: no connection is opened here.
    """
    try:
        return create_async_engine(_engine_url(database_url), pool_pre_ping=True)
    except ArgumentError:
        raise InvalidConfigError(
            "DATABASE_URL is malformed or uses an unsupported driver"
        ) from None


def _classify_driver_error(exc: BaseException) -> ProbeErrorCategory:
    if isinstance(exc, asyncpg.InvalidAuthorizationSpecificationError):
        return ProbeErrorCategory.AUTH
    if isinstance(exc, (asyncpg.PostgresConnectionError, OSError)):
        return ProbeErrorCategory.UNAVAILABLE
    if isinstance(exc, asyncpg.InterfaceError):
        return ProbeErrorCategory.UNAVAILABLE
    return ProbeErrorCategory.QUERY


def classify_probe_error(exc: BaseException) -> ProbeErrorCategory:
    """Map any probe failure to a stable, secret-free category.

    Driver exceptions are matched by type only; messages are never read,
    logged, or returned, because they can carry server-provided detail.
    """
    if isinstance(exc, (TimeoutError, SQLAlchemyTimeoutError)):
        return ProbeErrorCategory.TIMEOUT
    if isinstance(exc, DBAPIError):
        if exc.orig is not None:
            return _classify_driver_error(exc.orig)
        return ProbeErrorCategory.QUERY
    return _classify_driver_error(exc)


async def probe_postgres(engine: AsyncEngine) -> ProbeResult:
    """Run one bounded async ``SELECT 1`` against PostgreSQL.

    The whole attempt (connection checkout plus query) is bounded by
    ``PROBE_TIMEOUT_SECONDS`` and is never retried; a retried or prolonged
    readiness check would hide dependency outages. The result must be
    exactly ``1`` for the dependency to count as ready.
    """
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT 1"))
                value = result.scalar_one()
    except TimeoutError:
        return ProbeResult.failure(ProbeErrorCategory.TIMEOUT)
    except Exception as exc:  # mapped to safe categories; never surfaced
        return ProbeResult.failure(classify_probe_error(exc))
    if value != 1:
        return ProbeResult.failure(ProbeErrorCategory.QUERY)
    return ProbeResult.success()


def build_readiness_probe(engine: AsyncEngine | None) -> ProbeCallable:
    """Build the default readiness probe for application state.

    A missing engine means startup configuration was absent or invalid;
    the probe then reports the stable invalid-config category without
    touching the network.
    """

    async def _probe() -> ProbeResult:
        if engine is None:
            return ProbeResult.failure(ProbeErrorCategory.INVALID_CONFIG)
        return await probe_postgres(engine)

    return _probe
