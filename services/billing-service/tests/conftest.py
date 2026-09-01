"""Billing Service SF02 readiness test fixtures (T063).

Two fixture families:

* Fake-probe injection: scripted readiness outcomes (success, every failure
  category, timeout) installed through ``app.state`` without a real database.
* Real PostgreSQL: one disposable ``postgres:15.18-bookworm`` container named
  ``tmtest-<random>`` with a matching test label, a dynamic loopback port and
  a synthetic ``tm_local_`` password. Teardown removes only that exact
  labeled container.

Fixtures never expose URLs, credentials, or exception bodies to assertions or
logs. The container handle surfaces only safe identity fields (name, host,
port); URLs exist solely in memory to build engines or configure the service
under test and are never printed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.database import ProbeOutcome

_POSTGRES_IMAGE = "postgres:15.18-bookworm"
_TMTEST_LABEL = "tmtest.billing-readiness"


class ScriptedProbe:
    """Readiness probe double returning scripted outcomes, one per call."""

    def __init__(self, outcomes: list[ProbeOutcome], fallback: ProbeOutcome) -> None:
        self._outcomes: deque[ProbeOutcome] = deque(outcomes)
        self._fallback = fallback
        self.calls = 0

    async def __call__(self) -> ProbeOutcome:
        self.calls += 1
        if self._outcomes:
            return self._outcomes.popleft()
        return self._fallback


@pytest.fixture
def make_probe() -> Callable[..., ScriptedProbe]:
    """Build a scripted fake probe; falls back to success when exhausted."""

    def _factory(
        outcomes: list[ProbeOutcome] | None = None,
        fallback: ProbeOutcome | None = None,
    ) -> ScriptedProbe:
        from app.database import ProbeOutcome

        return ScriptedProbe(list(outcomes or []), fallback or ProbeOutcome(ok=True))

    return _factory


@contextlib.contextmanager
def _patched_state(pairs: dict[str, Any]) -> Iterator[None]:
    """Temporarily set ``app.state`` attributes, restoring them exactly."""
    missing = object()
    saved = {key: getattr(app.state, key, missing) for key in pairs}
    for key, value in pairs.items():
        setattr(app.state, key, value)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is missing:
                with contextlib.suppress(AttributeError):
                    delattr(app.state, key)
            else:
                setattr(app.state, key, value)


@pytest.fixture
def readiness_client() -> Callable[..., contextlib.AbstractContextManager[TestClient]]:
    """Build a lifespan-running TestClient with an injected probe/engine.

    With no arguments the real lifespan path runs and ``DATABASE_URL`` from
    the environment (controlled with ``monkeypatch``) decides the probe.
    """

    @contextlib.contextmanager
    def _client(probe: Any = None, engine: Any = None) -> Iterator[TestClient]:
        pairs: dict[str, Any] = {}
        if probe is not None:
            pairs["postgres_probe"] = probe
        if engine is not None:
            pairs["postgres_engine"] = engine
        with _patched_state(pairs):
            with TestClient(app) as client:
                yield client

    return _client


def _docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        _docker("info", timeout=15.0)
    except (subprocess.SubprocessError, OSError):
        return False
    return True


class PostgresContainer:
    """Safe handle over the disposable test PostgreSQL container."""

    def __init__(self, name: str, port: int, password: str) -> None:
        self.name = name
        self.host = "127.0.0.1"
        self.port = port
        self._username = "postgres"
        self._database = "postgres"
        self._password = password

    def __repr__(self) -> str:  # never includes credentials or the URL
        return f"PostgresContainer(name={self.name!r}, port={self.port})"

    def make_url(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> str:
        """Build a connection URL in memory only; never log or assert it."""
        return (
            f"postgresql://{username or self._username}:"
            f"{password or self._password}"
            f"@{self.host}:{self.port}/{database or self._database}"
        )

    @property
    def database_url(self) -> str:
        """URL for env injection or engine creation only; never log it."""
        return self.make_url()

    @contextlib.asynccontextmanager
    async def engine(self, **overrides: Any) -> AsyncIterator[AsyncEngine]:
        from app.database import create_postgres_engine

        engine = create_postgres_engine(self.make_url(**overrides))
        try:
            yield engine
        finally:
            await engine.dispose()

    def stop(self) -> None:
        _docker("stop", self.name, timeout=60.0)

    def start(self) -> None:
        """Sync start for sync fixtures; async tests use ``start_async``."""
        _docker("start", self.name, timeout=60.0)
        self.wait_ready()

    async def start_async(self) -> None:
        _docker("start", self.name, timeout=60.0)
        await self.wait_ready_async()

    def _pg_isready(self) -> bool:
        result = subprocess.run(
            [
                "docker",
                "exec",
                self.name,
                "pg_isready",
                "-U",
                self._username,
                "-d",
                self._database,
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        return result.returncode == 0

    def wait_ready(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._pg_isready():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"{self.name} did not report ready in time")
        while time.monotonic() < deadline:
            if asyncio.run(self._probe_once()):
                return
            time.sleep(0.5)
        raise RuntimeError(f"{self.name} rejected authenticated probes")

    async def wait_ready_async(self, timeout: float = 30.0) -> None:
        """Same wait as ``wait_ready`` but awaitable inside running loops."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await asyncio.to_thread(self._pg_isready):
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError(f"{self.name} did not report ready in time")
        while time.monotonic() < deadline:
            if await self._probe_once():
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"{self.name} rejected authenticated probes")

    async def _probe_once(self) -> bool:
        from app.database import create_postgres_engine, probe_postgres_readiness

        engine = create_postgres_engine(self.make_url())
        try:
            return (await probe_postgres_readiness(engine)).ok
        finally:
            await engine.dispose()


def _pick_loopback_port() -> int:
    """Choose a currently free loopback port for explicit publishing."""
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def _run_container(name: str, run_id: str, password: str) -> int:
    """Start the disposable container on an explicit loopback port.

    The port is published explicitly rather than ephemerally because Docker
    Desktop on macOS does not restore ephemeral ``127.0.0.1::5432`` forwards
    after container stop/start, which would break the recovery tests. The
    port number is still chosen dynamically per run; a bind race simply
    retries with a fresh port. Failure messages stay static so the synthetic
    password in the ``run`` argv can never reach test logs.
    """
    for _ in range(3):
        port = _pick_loopback_port()
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--pull",
                "never",
                "--name",
                name,
                "--label",
                f"{_TMTEST_LABEL}={run_id}",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "--mount",
                "type=tmpfs,destination=/var/lib/postgresql/data",
                "--publish",
                f"127.0.0.1:{port}:5432",
                _POSTGRES_IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        if result.returncode == 0:
            return port
        _remove_test_container(name, run_id)
    raise RuntimeError("disposable postgres container could not start")


def _remove_test_container(name: str, run_id: str) -> None:
    """Remove only the exact container this fixture created (hard guard)."""
    if not name.startswith("tmtest-"):
        return
    try:
        result = _docker(
            "inspect",
            name,
            "--format",
            "{{json .Config.Labels}}",
            timeout=15.0,
        )
        labels = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        return  # already gone or daemon unavailable; nothing safe to do
    if labels.get(_TMTEST_LABEL) != run_id:
        return
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60.0)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Disposable PostgreSQL 15.18 container; never pulls, always removes."""
    if not _docker_ok():
        pytest.skip("Docker daemon is not available")
    inspect = subprocess.run(
        ["docker", "image", "inspect", _POSTGRES_IMAGE],
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if inspect.returncode != 0:
        pytest.skip(f"{_POSTGRES_IMAGE} is not present and tests never pull")
    run_id = secrets.token_hex(4)
    name = f"tmtest-{run_id}"
    password = f"tm_local_{secrets.token_hex(20)}"
    port = _run_container(name, run_id, password)
    try:
        container = PostgresContainer(name, port, password)
        container.wait_ready()
        yield container
    finally:
        _remove_test_container(name, run_id)


@pytest.fixture
def hanging_tcp_sink() -> Iterator[tuple[str, int]]:
    """A loopback TCP listener that accepts but never answers (hangs PG)."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    listener.settimeout(0.2)
    accepted: list[socket.socket] = []
    stopping = threading.Event()

    def _accept_loop() -> None:
        while not stopping.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            accepted.append(conn)

    thread = threading.Thread(target=_accept_loop, daemon=True)
    thread.start()
    try:
        yield "127.0.0.1", int(listener.getsockname()[1])
    finally:
        stopping.set()
        thread.join(timeout=2.0)
        for conn in accepted:
            with contextlib.suppress(OSError):
                conn.close()
        listener.close()


@pytest.fixture
def unused_tcp_port() -> int:
    """A loopback port with nothing listening (closed before yielding)."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port
