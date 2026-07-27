"""Authentication integration fixtures (T008): testcontainers PG/Redis, factories.

Uses locked ``testcontainers[postgres,redis]==4.14.2``. Fixtures never log
connection URLs or secrets. Register via ``pytest_plugins`` in tests/conftest.py.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from app.dependencies import create_session_engine
from app.domain.users.models import User, UserRole, UserStatus
from tests.integration.conftest_register import run_alembic, unique_phone

POSTGRES_IMAGE = "postgres:15.18-bookworm"
REDIS_IMAGE = "redis:7.2-alpine"


@dataclass
class AuthPostgresHandle:
    """Disposable PostgreSQL 15.18 via testcontainers; password excluded from repr."""

    _container: Any = field(repr=False)
    host: str
    port: int
    user: str
    database: str
    _password: str = field(repr=False)

    def database_url(self) -> str:
        return (
            f"postgresql://{self.user}:{self._password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    def engine(self) -> Engine:
        return create_engine(self.database_url(), pool_pre_ping=True)

    def stop(self) -> None:
        self._container.stop()

    def start(self) -> None:
        """Restart container and refresh published host/port (may change)."""
        self._container.start()
        self.host = self._container.get_container_host_ip()
        self.port = int(self._container.get_exposed_port(5432))
        deadline = time.monotonic() + 60.0
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            engine = self.engine()
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return
            except Exception as exc:  # noqa: BLE001 — readiness probe
                last_err = exc
                time.sleep(0.25)
            finally:
                engine.dispose()
        raise RuntimeError(f"postgres container not ready after start: {last_err!r}")


@dataclass
class AuthRedisHandle:
    """Disposable Redis 7.2 via testcontainers."""

    _container: Any = field(repr=False)
    host: str
    port: int

    def redis_url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"

    def stop(self) -> None:
        self._container.stop()

    def start(self) -> None:
        """Restart container and refresh published host/port (may change)."""
        self._container.start()
        self.host = self._container.get_container_host_ip()
        self.port = int(self._container.get_exposed_port(6379))
        import redis as redis_lib

        deadline = time.monotonic() + 60.0
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            client = redis_lib.Redis(
                host=self.host, port=self.port, decode_responses=True
            )
            try:
                if client.ping():
                    return
            except Exception as exc:  # noqa: BLE001 — readiness probe
                last_err = exc
                time.sleep(0.25)
            finally:
                client.close()
        raise RuntimeError(f"redis container not ready after start: {last_err!r}")


class ControllableDbClock:
    """Read authoritative DB time; optional offset for freezegun-free clock tests."""

    def __init__(self, engine: Engine, *, offset: timedelta | None = None) -> None:
        self._engine = engine
        self.offset = offset or timedelta(0)

    def db_now(self) -> datetime:
        with self._engine.connect() as conn:
            value = conn.execute(text("SELECT NOW()")).scalar_one()
        assert isinstance(value, datetime)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value + self.offset

    def advance(self, delta: timedelta) -> None:
        self.offset += delta

    def set_offset(self, delta: timedelta) -> None:
        self.offset = delta


class AccountFactory:
    """Create active / suspended / deleted users; unknown = phone with no row."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factory = sessionmaker(engine, class_=Session, expire_on_commit=False)

    def create_active(
        self,
        *,
        phone: str | None = None,
        nickname: str = "活跃用户",
        role: UserRole = UserRole.buyer,
    ) -> User:
        return self._insert(
            phone=phone or unique_phone("138"),
            nickname=nickname,
            role=role,
            status=UserStatus.active,
            is_deleted=False,
        )

    def create_suspended(
        self,
        *,
        phone: str | None = None,
        nickname: str = "停用用户",
    ) -> User:
        return self._insert(
            phone=phone or unique_phone("137"),
            nickname=nickname,
            role=UserRole.buyer,
            status=UserStatus.suspended,
            is_deleted=False,
        )

    def create_deleted(
        self,
        *,
        phone: str | None = None,
        nickname: str = "已删用户",
    ) -> User:
        return self._insert(
            phone=phone or unique_phone("136"),
            nickname=nickname,
            role=UserRole.buyer,
            status=UserStatus.active,
            is_deleted=True,
        )

    def unknown_phone(self, prefix: str = "135") -> str:
        """Return a valid CN mobile that has no users row."""
        return unique_phone(prefix)

    def _insert(
        self,
        *,
        phone: str,
        nickname: str,
        role: UserRole,
        status: UserStatus,
        is_deleted: bool,
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            phone_normalized=phone,
            nickname=nickname,
            role=role,
            status=status,
            is_deleted=is_deleted,
            version=1,
        )
        with self._factory() as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            session.expunge(user)
        return user


class BlockingSmsFake:
    """SMS adapter fake that can block mid-send via asyncio.Event."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.gate.set()
        self.send_entered = asyncio.Event()
        self.calls: list[dict[str, Any]] = []
        self._result: str = "accepted"

    def block(self) -> None:
        self.gate.clear()
        self.send_entered.clear()

    def unblock(self) -> None:
        self.gate.set()

    def set_result(self, result: str) -> None:
        self._result = result

    async def send(
        self,
        *,
        destination_ref: bytes,
        code: str,
        provider_request_ref: uuid.UUID,
        timeout_seconds: float = 10.0,
    ) -> str:
        self.calls.append(
            {
                "destination_ref": destination_ref,
                "code_len": len(code),
                "provider_request_ref": provider_request_ref,
            }
        )
        self.send_entered.set()
        await self.gate.wait()
        return self._result


@dataclass
class DispatcherStub:
    """Minimal dispatcher claim/finalize stub for integration scaffolding."""

    owner: str = field(
        default_factory=lambda: f"test-dispatcher-{secrets.token_hex(4)}"
    )
    claimed: list[uuid.UUID] = field(default_factory=list)
    finalized: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    lease_seconds: int = 30

    def record_claim(self, challenge_id: uuid.UUID) -> None:
        self.claimed.append(challenge_id)

    def record_finalize(self, challenge_id: uuid.UUID, state: str) -> None:
        self.finalized.append((challenge_id, state))


@pytest.fixture
def auth_postgres_container() -> Iterator[AuthPostgresHandle]:
    """Spin up PostgreSQL 15.18 via testcontainers (no migrations)."""
    pytest.importorskip("testcontainers")
    from testcontainers.postgres import PostgresContainer

    password = f"tm_local_{secrets.token_urlsafe(24)}"
    container = PostgresContainer(
        image=POSTGRES_IMAGE,
        username="tmtest",
        password=password,
        dbname="tmtest",
        driver=None,
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(5432))
        handle = AuthPostgresHandle(
            _container=container,
            host=host,
            port=port,
            user="tmtest",
            database="tmtest",
            _password=password,
        )
        # Sanity: accept connections
        engine = handle.engine()
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        yield handle
    finally:
        container.stop()


@pytest.fixture
def auth_redis_container() -> Iterator[AuthRedisHandle]:
    """Spin up Redis 7.2 via testcontainers."""
    pytest.importorskip("testcontainers")
    from testcontainers.redis import RedisContainer

    container = RedisContainer(image=REDIS_IMAGE)
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(6379))
        handle = AuthRedisHandle(_container=container, host=host, port=port)
        import redis as redis_lib

        client = redis_lib.Redis(host=host, port=port, decode_responses=True)
        try:
            assert client.ping() is True
        finally:
            client.close()
        yield handle
    finally:
        container.stop()


@pytest.fixture
def auth_migrated_postgres(
    auth_postgres_container: AuthPostgresHandle,
) -> Iterator[str]:
    """PostgreSQL with Alembic migrations applied to head; yields DATABASE_URL."""
    url = auth_postgres_container.database_url()
    result = run_alembic(url, "upgrade", "head")
    assert (
        result.returncode == 0
    ), f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"
    yield url


@pytest.fixture
def auth_db_engine(auth_migrated_postgres: str) -> Iterator[Engine]:
    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_clock(auth_db_engine: Engine) -> ControllableDbClock:
    return ControllableDbClock(auth_db_engine)


@pytest.fixture
def account_factory(auth_db_engine: Engine) -> AccountFactory:
    return AccountFactory(auth_db_engine)


@pytest.fixture
def blocking_sms_fake() -> BlockingSmsFake:
    return BlockingSmsFake()


@pytest.fixture
def dispatcher_stub() -> DispatcherStub:
    return DispatcherStub()


@pytest.fixture
async def auth_db_session(
    auth_migrated_postgres: str,
) -> AsyncIterator[AsyncSession]:
    engine = create_session_engine(auth_migrated_postgres)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def auth_env(
    auth_migrated_postgres: str,
    auth_redis_container: AuthRedisHandle,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, str]]:
    """Set DATABASE_URL + REDIS_URL for auth integration HTTP tests."""
    env = {
        "DATABASE_URL": auth_migrated_postgres,
        "REDIS_URL": auth_redis_container.redis_url(),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    yield env
