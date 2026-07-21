"""PostgreSQL readiness probe and engine tests for api-service (SF02).

Covers safe URL-to-asyncpg driver mapping, the lifespan-owned engine with
``pool_pre_ping``, the bounded single-attempt ``SELECT 1`` probe, stable
secret-free error categories, shutdown disposal, and recovery against a real
disposable PostgreSQL container.
"""

from __future__ import annotations

import time

import asyncpg
import pytest
from conftest import MakeClient, PostgresHandle
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app import database
from app.database import (
    InvalidConfigError,
    ProbeErrorCategory,
    classify_probe_error,
    create_readiness_engine,
    probe_postgres,
)

SAFE_URL = "postgresql://probe_user:tm_local_synthetic@127.0.0.1:5432/probe_db"


def test_engine_factory_maps_postgresql_scheme_to_asyncpg() -> None:
    engine = create_readiness_engine(SAFE_URL)
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.host == "127.0.0.1"
        assert engine.url.port == 5432
        assert engine.url.database == "probe_db"
        assert engine.url.username == "probe_user"
    finally:
        engine.sync_engine.dispose()


def test_engine_factory_accepts_asyncpg_scheme_unchanged() -> None:
    engine = create_readiness_engine(
        "postgresql+asyncpg://probe_user:tm_local_synthetic@127.0.0.1:5432/probe_db"
    )
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
    finally:
        engine.sync_engine.dispose()


def test_engine_factory_enables_pool_pre_ping() -> None:
    engine = create_readiness_engine(SAFE_URL)
    try:
        assert getattr(engine.pool, "_pre_ping", None) is True
    finally:
        engine.sync_engine.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg2://probe_user:tm_local_synthetic@127.0.0.1:5432/db",
        "postgresql+pg8000://probe_user:tm_local_synthetic@127.0.0.1:5432/db",
        "sqlite:///probe.db",
        "mysql://probe_user:tm_local_synthetic@127.0.0.1:3306/db",
        "not a url",
        "",
    ],
)
def test_engine_factory_rejects_unsupported_or_malformed_urls(url: str) -> None:
    with pytest.raises(InvalidConfigError) as excinfo:
        create_readiness_engine(url)
    message = str(excinfo.value).lower()
    assert "postgresql" not in message
    assert "probe_user" not in message
    assert "tm_local_synthetic" not in message
    assert "127.0.0.1" not in message


def test_classify_timeout_errors() -> None:
    assert classify_probe_error(TimeoutError()) is ProbeErrorCategory.TIMEOUT


def test_classify_auth_errors() -> None:
    wrapped = OperationalError(
        "SELECT 1", {}, asyncpg.InvalidPasswordError("synthetic")
    )
    assert classify_probe_error(wrapped) is ProbeErrorCategory.AUTH
    assert (
        classify_probe_error(asyncpg.InvalidAuthorizationSpecificationError("s"))
        is ProbeErrorCategory.AUTH
    )


def test_classify_unavailable_errors() -> None:
    wrapped = OperationalError("SELECT 1", {}, OSError("synthetic refused"))
    assert classify_probe_error(wrapped) is ProbeErrorCategory.UNAVAILABLE
    assert (
        classify_probe_error(asyncpg.PostgresConnectionError("synthetic"))
        is ProbeErrorCategory.UNAVAILABLE
    )


def test_classify_query_errors() -> None:
    wrapped = OperationalError("SELECT 1", {}, Exception("synthetic"))
    assert classify_probe_error(wrapped) is ProbeErrorCategory.QUERY
    assert (
        classify_probe_error(asyncpg.UndefinedTableError("synthetic"))
        is ProbeErrorCategory.QUERY
    )


async def test_probe_refused_connection_maps_to_unavailable(
    unused_loopback_port: int,
) -> None:
    engine = create_readiness_engine(
        "postgresql://probe_user:tm_local_synthetic@127.0.0.1:"
        f"{unused_loopback_port}/probe_db"
    )
    try:
        started = time.monotonic()
        result = await probe_postgres(engine)
        elapsed = time.monotonic() - started
    finally:
        await engine.dispose()
    assert not result.ok
    assert result.category is ProbeErrorCategory.UNAVAILABLE
    assert elapsed < database.PROBE_TIMEOUT_SECONDS


async def test_probe_enforces_two_second_bound(blackhole_port: int) -> None:
    engine = create_readiness_engine(
        "postgresql://probe_user:tm_local_synthetic@127.0.0.1:"
        f"{blackhole_port}/probe_db"
    )
    try:
        started = time.monotonic()
        result = await probe_postgres(engine)
        elapsed = time.monotonic() - started
    finally:
        await engine.dispose()
    assert not result.ok
    assert result.category is ProbeErrorCategory.TIMEOUT
    assert database.PROBE_TIMEOUT_SECONDS <= elapsed
    assert elapsed < database.PROBE_TIMEOUT_SECONDS + 1.0


async def test_probe_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def counting_connect(self: AsyncEngine) -> object:
        nonlocal attempts
        attempts += 1
        raise OSError("synthetic connection failure")

    monkeypatch.setattr(AsyncEngine, "connect", counting_connect)
    engine = create_readiness_engine(SAFE_URL)
    try:
        result = await probe_postgres(engine)
    finally:
        await engine.dispose()
    assert attempts == 1
    assert not result.ok
    assert result.category is ProbeErrorCategory.UNAVAILABLE


async def test_probe_requires_exact_select_one_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        def scalar_one(self) -> int:
            return 2

    class FakeConnection:
        async def execute(self, clause: object) -> FakeResult:
            return FakeResult()

        async def __aenter__(self) -> "FakeConnection":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(AsyncEngine, "connect", lambda self: FakeConnection())
    engine = create_readiness_engine(SAFE_URL)
    try:
        result = await probe_postgres(engine)
    finally:
        await engine.dispose()
    assert not result.ok
    assert result.category is ProbeErrorCategory.QUERY


async def test_probe_succeeds_against_real_postgres(
    postgres_container: PostgresHandle,
) -> None:
    engine = create_readiness_engine(postgres_container.database_url())
    try:
        started = time.monotonic()
        result = await probe_postgres(engine)
        elapsed = time.monotonic() - started
    finally:
        await engine.dispose()
    assert result.ok
    assert result.category is None
    assert elapsed < database.PROBE_TIMEOUT_SECONDS


async def test_probe_wrong_password_maps_to_auth(
    postgres_container: PostgresHandle,
) -> None:
    engine = create_readiness_engine(
        postgres_container.database_url(password="tm_local_wrong_synthetic_value")
    )
    try:
        result = await probe_postgres(engine)
    finally:
        await engine.dispose()
    assert not result.ok
    assert result.category is ProbeErrorCategory.AUTH


async def test_lifespan_owns_engine_and_disposes_on_shutdown(
    make_client: MakeClient,
    postgres_container: PostgresHandle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed: list[AsyncEngine] = []
    original_dispose = AsyncEngine.dispose

    async def spy_dispose(self: AsyncEngine) -> None:
        disposed.append(self)
        await original_dispose(self)

    monkeypatch.setattr(AsyncEngine, "dispose", spy_dispose)
    with make_client(
        database_url=postgres_container.database_url(), inject_probe=False
    ) as handle:
        engine = handle.client.app.state.db_engine
        assert isinstance(engine, AsyncEngine)
        assert engine.url.drivername == "postgresql+asyncpg"
        first = handle.client.get("/health/ready")
        second = handle.client.get("/health/ready")
        assert handle.client.app.state.db_engine is engine
    assert first.status_code == 200
    assert second.status_code == 200
    assert engine in disposed


def test_real_postgres_outage_and_recovery_without_service_restart(
    make_client: MakeClient,
    postgres_container: PostgresHandle,
) -> None:
    with make_client(
        database_url=postgres_container.database_url(), inject_probe=False
    ) as handle:
        ready = handle.client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        postgres_container.stop()
        try:
            started = time.monotonic()
            outage = handle.client.get("/health/ready")
            elapsed = time.monotonic() - started
        finally:
            postgres_container.start()
        assert outage.status_code == 503
        assert elapsed < database.PROBE_TIMEOUT_SECONDS + 1.0
        payload = outage.json()
        assert payload["dependencies"] == [
            {
                "name": "postgres",
                "status": "not_ready",
                "code": "DEPENDENCY_NOT_READY",
            }
        ]

        recovered = handle.client.get("/health/ready")
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "ready"
        assert set(recovered.json()) == {
            "service",
            "status",
            "version",
            "request_id",
        }


def test_real_postgres_wrong_password_returns_dependency_not_ready(
    make_client: MakeClient,
    postgres_container: PostgresHandle,
) -> None:
    wrong_url = postgres_container.database_url(
        password="tm_local_wrong_synthetic_value"
    )
    with make_client(database_url=wrong_url, inject_probe=False) as handle:
        live = handle.client.get("/health/live")
        ready = handle.client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 503
    payload = ready.json()
    assert payload["dependencies"] == [
        {"name": "postgres", "status": "not_ready", "code": "DEPENDENCY_NOT_READY"}
    ]
    assert "tm_local_wrong_synthetic_value" not in ready.text
