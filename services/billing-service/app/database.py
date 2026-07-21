"""Billing Service owned asynchronous PostgreSQL readiness probe (SF02).

The service lifespan creates the engine on startup and disposes it on
shutdown. Each readiness request runs one fresh, bounded ``SELECT 1`` probe
with an overall two-second timeout and no retries. Every failure maps to a
stable, safe category; no URL, username, password, SQL, or exception body
ever leaves this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PROBE_TIMEOUT_SECONDS = 2.0

# Driver exceptions arrive wrapped in SQLAlchemy's DBAPIError. Classification
# matches the asyncpg exception class names through the MRO so the driver
# module is never imported and exception text is never inspected.
_AUTH_ERROR_CLASS_NAMES = frozenset(
    {"InvalidPasswordError", "InvalidAuthorizationSpecificationError"}
)
_QUERY_ERROR_CLASS_NAMES = frozenset({"PostgresError"})
_INTERFACE_ERROR_CLASS_NAMES = frozenset({"InterfaceError"})


class ProbeErrorCategory(str, Enum):
    """Stable safe probe failure categories (never serialized raw)."""

    INVALID_CONFIG = "invalid_config"
    AUTH = "auth"
    QUERY = "query"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of one probe attempt; carries no diagnostic payload."""

    ok: bool
    category: ProbeErrorCategory | None = None


ReadinessProbe = Callable[[], Awaitable[ProbeOutcome]]


class InvalidDatabaseConfigError(Exception):
    """DATABASE_URL is unusable; the message is static and never echoes it."""


def map_database_url(database_url: str) -> URL:
    """Map a PostgreSQL URL onto the asyncpg driver, rejecting unsafe input.

    Only ``postgresql://`` (rewritten) and ``postgresql+asyncpg://`` are
    accepted. Malformed URLs, sync or foreign drivers, and missing
    username/password/host/database raise ``InvalidDatabaseConfigError``
    whose message never contains the URL or any credential.
    """
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise InvalidDatabaseConfigError(
            "DATABASE_URL is not a parseable URL"
        ) from None
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    elif url.drivername != "postgresql+asyncpg":
        raise InvalidDatabaseConfigError(
            "DATABASE_URL must use the PostgreSQL async driver"
        )
    if not url.username or not url.password or not url.host or not url.database:
        raise InvalidDatabaseConfigError(
            "DATABASE_URL requires username, password, host, and database"
        )
    return url


def create_postgres_engine(database_url: str) -> AsyncEngine:
    """Create the lifespan-owned async engine with pool pre-ping enabled."""
    return create_async_engine(map_database_url(database_url), pool_pre_ping=True)


def _driver_error_category(orig: BaseException) -> ProbeErrorCategory:
    names = {cls.__name__ for cls in type(orig).__mro__}
    if names & _AUTH_ERROR_CLASS_NAMES:
        return ProbeErrorCategory.AUTH
    if isinstance(orig, OSError) or names & _INTERFACE_ERROR_CLASS_NAMES:
        return ProbeErrorCategory.UNAVAILABLE
    if names & _QUERY_ERROR_CLASS_NAMES:
        return ProbeErrorCategory.QUERY
    return ProbeErrorCategory.UNAVAILABLE


def categorize_probe_error(exc: BaseException) -> ProbeErrorCategory:
    """Map any probe failure to a stable safe category.

    Only exception types and driver class names are consulted; exception
    messages are never read, logged, or returned. asyncpg raises connect-time
    failures (authentication, catalog, refused connections) unwrapped, so
    bare driver exceptions are classified exactly like DBAPIError-wrapped
    ones.
    """
    if isinstance(exc, TimeoutError):
        return ProbeErrorCategory.TIMEOUT
    if isinstance(exc, DBAPIError):
        if exc.orig is not None:
            return _driver_error_category(exc.orig)
        return ProbeErrorCategory.UNAVAILABLE
    return _driver_error_category(exc)


async def probe_postgres_readiness(engine: AsyncEngine) -> ProbeOutcome:
    """Run one bounded ``SELECT 1`` against PostgreSQL; never retried."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                value = await connection.scalar(text("SELECT 1"))
    except TimeoutError:
        return ProbeOutcome(ok=False, category=ProbeErrorCategory.TIMEOUT)
    except Exception as exc:
        return ProbeOutcome(ok=False, category=categorize_probe_error(exc))
    if value == 1:
        return ProbeOutcome(ok=True)
    return ProbeOutcome(ok=False, category=ProbeErrorCategory.QUERY)
