"""Shared helpers for registration integration tests (import from test modules)."""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import create_session_engine
from app.main import app
from app.rate_limit import MemoryRateLimiter
from tests.conftest import PostgresHandle

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        ["uv", "run", "--locked", "alembic", *args],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def migrated_postgres(postgres_container: PostgresHandle) -> Iterator[str]:
    """Disposable PG with migrations applied to head; yields sync DATABASE_URL."""
    url = postgres_container.database_url()
    result = run_alembic(url, "upgrade", "head")
    assert (
        result.returncode == 0
    ), f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"
    yield url


@pytest.fixture
def register_client(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", migrated_postgres)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(app) as client:
        client.app.state.rate_limiter = MemoryRateLimiter()
        yield client


@pytest.fixture
async def db_session(migrated_postgres: str) -> AsyncIterator[AsyncSession]:
    engine = create_session_engine(migrated_postgres)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def unique_phone(prefix: str = "139") -> str:
    """Generate a unique valid CN mobile (1[3-9]…)."""
    body = f"{uuid.uuid4().int % 10**8:08d}"
    return (prefix + body)[:11]
