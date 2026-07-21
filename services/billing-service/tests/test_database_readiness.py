"""Billing Service PostgreSQL readiness database tests (SF02/T055).

Covers safe URL driver mapping, the lifespan-owned engine with
``pool_pre_ping``, the bounded async ``SELECT 1`` probe with no retries,
shutdown disposal, safe error categories, and recovery against a real
disposable PostgreSQL container.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError

from app.database import (
    InvalidDatabaseConfigError,
    ProbeErrorCategory,
    categorize_probe_error,
    create_postgres_engine,
    map_database_url,
    probe_postgres_readiness,
)
from app.main import app


class InvalidPasswordError(Exception):
    """Driver-name double for the asyncpg authentication error hierarchy."""


class InvalidAuthorizationSpecificationError(Exception):
    """Driver-name double for the asyncpg authorization base error."""


class PostgresError(Exception):
    """Driver-name double for server-raised asyncpg errors."""


class InterfaceError(Exception):
    """Driver-name double for asyncpg client-side connection errors."""


def _dbapi_error(orig: BaseException) -> DBAPIError:
    return DBAPIError("SELECT 1", {}, orig)


# --- Safe URL driver mapping -------------------------------------------------


def test_plain_postgresql_url_maps_to_asyncpg_driver() -> None:
    url = map_database_url("postgresql://billing:pw@127.0.0.1:5432/billing")
    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "billing"
    assert url.host == "127.0.0.1"
    assert url.port == 5432
    assert url.database == "billing"


def test_asyncpg_url_is_accepted_unchanged() -> None:
    url = map_database_url("postgresql+asyncpg://billing:pw@127.0.0.1:5432/db")
    assert url.drivername == "postgresql+asyncpg"


@pytest.mark.parametrize(
    "rejected",
    [
        "postgresql+psycopg2://u:p@127.0.0.1:5432/db",
        "postgresql+psycopg://u:p@127.0.0.1:5432/db",
        "postgresql+pg8000://u:p@127.0.0.1:5432/db",
        "mysql://u:p@127.0.0.1:3306/db",
        "sqlite:///tmp.db",
    ],
)
def test_sync_and_foreign_drivers_are_rejected(rejected: str) -> None:
    with pytest.raises(InvalidDatabaseConfigError):
        map_database_url(rejected)


def test_malformed_url_is_rejected() -> None:
    with pytest.raises(InvalidDatabaseConfigError):
        map_database_url("not a database url")


@pytest.mark.parametrize(
    "rejected",
    [
        "postgresql://:pw@127.0.0.1:5432/db",  # missing username
        "postgresql://user@127.0.0.1:5432/db",  # missing password
        "postgresql://user:pw@/db",  # missing host
        "postgresql://user:pw@127.0.0.1:5432/",  # missing database
    ],
)
def test_incomplete_urls_are_rejected(rejected: str) -> None:
    with pytest.raises(InvalidDatabaseConfigError):
        map_database_url(rejected)


def test_config_errors_never_echo_url_or_secrets() -> None:
    canary = "tm_local_canarysecret123"
    with pytest.raises(InvalidDatabaseConfigError) as excinfo:
        map_database_url(f"postgresql+psycopg2://user:{canary}@127.0.0.1:9/db")
    message = str(excinfo.value)
    assert canary not in message
    assert "psycopg2" not in message
    assert "127.0.0.1" not in message
    assert excinfo.value.__cause__ is None
    with pytest.raises(InvalidDatabaseConfigError) as malformed:
        map_database_url(canary)
    assert canary not in str(malformed.value)
    assert malformed.value.__suppress_context__ is True


def test_engine_uses_asyncpg_driver_and_pool_pre_ping() -> None:
    engine = create_postgres_engine("postgresql://billing:pw@127.0.0.1:5432/db")
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.sync_engine.pool._pre_ping is True
    finally:
        import asyncio

        asyncio.run(engine.dispose())


# --- Safe error categories ----------------------------------------------------


def test_timeout_maps_to_timeout_category() -> None:
    assert categorize_probe_error(TimeoutError()) is ProbeErrorCategory.TIMEOUT


def test_driver_auth_errors_map_to_auth_category() -> None:
    outcome = categorize_probe_error(_dbapi_error(InvalidPasswordError("x")))
    assert outcome is ProbeErrorCategory.AUTH
    outcome = categorize_probe_error(
        _dbapi_error(InvalidAuthorizationSpecificationError("x"))
    )
    assert outcome is ProbeErrorCategory.AUTH


def test_driver_server_errors_map_to_query_category() -> None:
    outcome = categorize_probe_error(_dbapi_error(PostgresError("x")))
    assert outcome is ProbeErrorCategory.QUERY


def test_connection_failures_map_to_unavailable_category() -> None:
    outcome = categorize_probe_error(_dbapi_error(ConnectionRefusedError()))
    assert outcome is ProbeErrorCategory.UNAVAILABLE
    outcome = categorize_probe_error(_dbapi_error(InterfaceError("x")))
    assert outcome is ProbeErrorCategory.UNAVAILABLE
    outcome = categorize_probe_error(OSError("network down"))
    assert outcome is ProbeErrorCategory.UNAVAILABLE


def test_unknown_errors_map_to_unavailable_without_details() -> None:
    outcome = categorize_probe_error(RuntimeError("tm_local_never_surfaces"))
    assert outcome is ProbeErrorCategory.UNAVAILABLE


# --- Probe behavior with a stub engine (no real database) --------------------


class _StubConnection:
    def __init__(self, value: Any = None, error: BaseException | None = None):
        self._value = value
        self._error = error

    async def scalar(self, statement: Any) -> Any:
        if self._error is not None:
            raise self._error
        return self._value


class _StubConnect:
    def __init__(self, connection: _StubConnection):
        self._connection = connection

    async def __aenter__(self) -> _StubConnection:
        if self._connection._error is not None:
            raise self._connection._error
        return self._connection

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


class _StubEngine:
    def __init__(self, connection: _StubConnection):
        self._connection = connection
        self.connect_calls = 0

    def connect(self) -> _StubConnect:
        self.connect_calls += 1
        return _StubConnect(self._connection)


@pytest.mark.asyncio
async def test_probe_requires_exact_select_one_result() -> None:
    outcome = await probe_postgres_readiness(_StubEngine(_StubConnection(value=1)))
    assert outcome.ok
    assert outcome.category is None


@pytest.mark.asyncio
async def test_probe_rejects_unexpected_scalar_result() -> None:
    outcome = await probe_postgres_readiness(_StubEngine(_StubConnection(value=2)))
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.QUERY


@pytest.mark.asyncio
async def test_probe_makes_exactly_one_attempt_without_retry() -> None:
    engine = _StubEngine(_StubConnection(error=ConnectionRefusedError()))
    outcome = await probe_postgres_readiness(engine)
    assert engine.connect_calls == 1
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.UNAVAILABLE


# --- Bounded probe against local sockets --------------------------------------


@pytest.mark.asyncio
async def test_probe_is_bounded_at_two_seconds(hanging_tcp_sink) -> None:
    host, port = hanging_tcp_sink
    engine = create_postgres_engine(f"postgresql://billing:pw@{host}:{port}/db")
    start = time.monotonic()
    try:
        outcome = await probe_postgres_readiness(engine)
        elapsed = time.monotonic() - start
    finally:
        await engine.dispose()
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.TIMEOUT
    assert 1.0 < elapsed < 10.0


@pytest.mark.asyncio
async def test_probe_reports_refused_connection_as_unavailable(
    unused_tcp_port: int,
) -> None:
    engine = create_postgres_engine(
        f"postgresql://billing:pw@127.0.0.1:{unused_tcp_port}/db"
    )
    try:
        outcome = await probe_postgres_readiness(engine)
    finally:
        await engine.dispose()
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.UNAVAILABLE


# --- Real disposable PostgreSQL ----------------------------------------------


@pytest.mark.asyncio
async def test_real_postgres_probe_succeeds_within_bound(
    postgres_container,
) -> None:
    async with postgres_container.engine() as engine:
        start = time.monotonic()
        outcome = await probe_postgres_readiness(engine)
        elapsed = time.monotonic() - start
    assert outcome.ok
    assert outcome.category is None
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_real_postgres_wrong_password_maps_to_auth(
    postgres_container,
) -> None:
    wrong = "tm_local_wrongpassword000000000000000000000000"
    async with postgres_container.engine(password=wrong) as engine:
        outcome = await probe_postgres_readiness(engine)
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.AUTH


@pytest.mark.asyncio
async def test_real_postgres_unknown_database_maps_to_query(
    postgres_container,
) -> None:
    async with postgres_container.engine(database="tmtest_missing_db") as engine:
        outcome = await probe_postgres_readiness(engine)
    assert not outcome.ok
    assert outcome.category is ProbeErrorCategory.QUERY


@pytest.mark.asyncio
async def test_real_postgres_recovers_without_engine_recreation(
    postgres_container,
) -> None:
    async with postgres_container.engine() as engine:
        assert (await probe_postgres_readiness(engine)).ok
        postgres_container.stop()
        try:
            outcome = await probe_postgres_readiness(engine)
            assert not outcome.ok
            assert outcome.category is ProbeErrorCategory.UNAVAILABLE
        finally:
            await postgres_container.start_async()
        outcome = await probe_postgres_readiness(engine)
        assert outcome.ok


# --- Lifespan ownership and shutdown disposal ---------------------------------


def test_lifespan_creates_uses_and_disposes_engine(
    postgres_container,
    readiness_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed: list[bool] = []
    monkeypatch.setenv("DATABASE_URL", postgres_container.database_url)
    with readiness_client() as client:
        engine = app.state.postgres_engine
        assert engine is not None
        event.listen(
            engine.sync_engine,
            "engine_disposed",
            lambda _engine: disposed.append(True),
        )
        assert client.get("/health/ready").status_code == 200
    assert disposed == [True]
    assert app.state.postgres_engine is None
    assert app.state.postgres_probe is None


def test_lifespan_disposes_injected_engine_on_shutdown(readiness_client) -> None:
    disposed: list[bool] = []
    engine = create_postgres_engine("postgresql://billing:pw@127.0.0.1:5432/db")
    event.listen(
        engine.sync_engine,
        "engine_disposed",
        lambda _engine: disposed.append(True),
    )

    async def _ok_probe() -> Any:
        from app.database import ProbeOutcome

        return ProbeOutcome(ok=True)

    with readiness_client(_ok_probe, engine) as client:
        assert client.get("/health/ready").status_code == 200
    assert disposed == [True]
