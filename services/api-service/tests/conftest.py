"""Shared fixtures for api-service readiness tests (SF02).

Two fixture families:

* Scripted fake readiness probes injected through ``app.state`` so contract
  and observability tests run without a real database.
* A disposable, exactly-labelled ``postgres:15.18-bookworm`` container with a
  dynamic loopback port and synthetic ``tm_local_`` credentials for real
  PostgreSQL integration tests.

Fixtures never log connection URLs or exception bodies, and teardown removes
only the exact test-labelled container each fixture created.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.database import ProbeResult
from app.main import app

# Re-export integration plugins for pytest discovery under tests/integration/
pytest_plugins = [
    "tests.integration.conftest_register",
    "tests.integration.conftest_authentication",
    "tests.integration.conftest_authorization",
]

POSTGRES_IMAGE = "postgres:15.18-bookworm"
TEST_LABEL_KEY = "tmtest"
TEST_LABEL_VALUE = "api-service-readiness"
CONTAINER_PREFIX = "tmtest-"


class ScriptedProbe:
    """Scripted readiness probe outcomes injected via application state.

    Each call pops the next scripted outcome; once the script is exhausted
    the probe reports success, which models dependency recovery.
    """

    def __init__(self) -> None:
        self.calls = 0
        self._outcomes: list[ProbeResult] = []

    def set_outcomes(self, *outcomes: ProbeResult) -> None:
        self._outcomes = list(outcomes)

    async def __call__(self) -> ProbeResult:
        self.calls += 1
        if not self._outcomes:
            return ProbeResult.success()
        return self._outcomes.pop(0)


@dataclass
class ClientHandle:
    client: TestClient
    probe: Any


MakeClient = Callable[..., contextlib.AbstractContextManager[ClientHandle]]


@pytest.fixture
def make_client() -> MakeClient:
    """Build a TestClient with controlled env and an injectable probe.

    ``DATABASE_URL`` is deleted unless a value is passed, so tests are
    hermetic regardless of the developer environment. With
    ``inject_probe=True`` (default) a scripted fake probe replaces the
    service-owned PostgreSQL probe; pass ``inject_probe=False`` to exercise
    the real lifespan engine and probe.
    """

    @contextlib.contextmanager
    def _make(
        database_url: str | None = None,
        *,
        inject_probe: bool = True,
        probe: Any = None,
    ) -> Iterator[ClientHandle]:
        with pytest.MonkeyPatch.context() as monkey:
            if database_url is None:
                monkey.delenv("DATABASE_URL", raising=False)
            else:
                monkey.setenv("DATABASE_URL", database_url)
            with TestClient(app) as client:
                scripted = probe if probe is not None else ScriptedProbe()
                if inject_probe:
                    client.app.state.readiness_probe = scripted
                yield ClientHandle(client=client, probe=scripted)

    return _make


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def unused_loopback_port() -> int:
    """A loopback port with no listener (connections are refused)."""
    return _free_loopback_port()


@pytest.fixture
def blackhole_port() -> Iterator[int]:
    """Loopback listener that accepts connections but never responds."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    server.settimeout(0.1)
    port = int(server.getsockname()[1])
    stopping = threading.Event()
    held: list[socket.socket] = []

    def _hold_connections() -> None:
        while not stopping.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            held.append(conn)

    thread = threading.Thread(target=_hold_connections, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stopping.set()
        server.close()
        for conn in held:
            conn.close()
        thread.join(timeout=2)


def _docker(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", *args], capture_output=True, timeout=90, check=False
    )


@dataclass
class PostgresHandle:
    """Control handle for one disposable test PostgreSQL container.

    The password is a synthetic ``tm_local_`` value excluded from repr;
    connection URLs are built on demand and never logged or asserted on.
    """

    name: str
    port: int
    user: str
    database: str
    _password: str = field(repr=False)
    host: str = "127.0.0.1"

    def database_url(self, *, password: str | None = None) -> str:
        secret = self._password if password is None else password
        return (
            f"postgresql://{self.user}:{secret}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    def stop(self) -> None:
        _docker("stop", self.name)

    def start(self) -> None:
        _docker("start", self.name)
        _wait_until_ready(self)


def _remove_test_container(name: str) -> None:
    """Remove only the exact test-labelled container a fixture created."""
    if not name.startswith(CONTAINER_PREFIX):
        return
    inspect = _docker(
        "inspect",
        "--format",
        '{{index .Config.Labels "' + TEST_LABEL_KEY + '"}}',
        name,
    )
    if inspect.returncode != 0:
        return
    if inspect.stdout.decode("utf-8", "replace").strip() != TEST_LABEL_VALUE:
        return
    _docker("rm", "--force", name)


def _verify_authenticated_query(handle: PostgresHandle) -> bool:
    async def _check() -> bool:
        connection: asyncpg.Connection[Any] | None = None
        try:
            connection = await asyncpg.connect(
                host=handle.host,
                port=handle.port,
                user=handle.user,
                password=handle._password,
                database=handle.database,
                timeout=5,
            )
            return bool(await connection.fetchval("SELECT 1") == 1)
        except Exception:
            return False
        finally:
            if connection is not None:
                await connection.close()

    try:
        return asyncio.run(_check())
    except Exception:
        return False


def _wait_until_ready(handle: PostgresHandle, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = _docker(
            "exec",
            handle.name,
            "pg_isready",
            "-U",
            handle.user,
            "-d",
            handle.database,
        )
        if ready.returncode == 0 and _verify_authenticated_query(handle):
            return
        time.sleep(0.5)
    pytest.fail("disposable postgres test container did not become ready")


@pytest.fixture
def postgres_container() -> Iterator[PostgresHandle]:
    """Spin up a disposable, exactly-labelled PostgreSQL 15.18 container."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI unavailable")
    if _docker("info", "--format", "{{.ServerVersion}}").returncode != 0:
        pytest.skip("local docker runtime unavailable")
    handle = PostgresHandle(
        name=f"{CONTAINER_PREFIX}{secrets.token_hex(8)}",
        port=_free_loopback_port(),
        user="tmtest",
        database="tmtest",
        _password=f"tm_local_{secrets.token_urlsafe(24)}",
    )
    started = _docker(
        "run",
        "--detach",
        "--name",
        handle.name,
        "--label",
        f"{TEST_LABEL_KEY}={TEST_LABEL_VALUE}",
        "--env",
        f"POSTGRES_USER={handle.user}",
        "--env",
        f"POSTGRES_PASSWORD={handle._password}",
        "--env",
        f"POSTGRES_DB={handle.database}",
        "--publish",
        f"127.0.0.1:{handle.port}:5432",
        POSTGRES_IMAGE,
    )
    try:
        if started.returncode != 0:
            pytest.fail("failed to start disposable postgres test container")
        _wait_until_ready(handle)
        yield handle
    finally:
        _remove_test_container(handle.name)
