"""Bounded authenticated readiness probe tests (T023).

Covers research Decision 10 and the readiness contract of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``:

- PostgreSQL: the configured user/password/database authenticates over TCP and
  ``SELECT 1`` must return exactly ``1``; any other result is rejected.
- Redis: AUTH with the URL password and PING must succeed on one and the same
  connection; only ``PONG`` is accepted; cross-connection evidence is stale.
- Grafana: unauthenticated ``GET /api/health`` must be 200 with
  ``database == "ok"`` AND Basic-auth ``GET /api/user`` must be 200 with
  ``isGrafanaAdmin == true``; both are required.
- Every attempt is bounded by ``min(probe timeout, deadline - monotonic_now)``;
  truncation is exact, retries stop at the shared deadline or on unretryable
  categories, and no post-deadline result can flip a run to success.
- Every outcome maps to a stable v2 diagnostic category whose bounded reason
  never contains secrets, URLs with user-info, absolute paths, exception
  bodies, or raw HTTP/health output.

All network access is replaced by injected fake transports; no test touches
Docker or a real socket. Deadline control uses the shared ``MonotonicClock``.

These tests fail until T029 implements ``tools/workflow/local_env/probes.py``.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
from collections import deque
from datetime import datetime, timezone
from typing import Any

import asyncpg
import pytest

from workflow import events
from workflow.local_env import models


def _probes() -> Any:
    try:
        return importlib.import_module("workflow.local_env.probes")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.probes is not implemented yet (T029): {exc}")


FIXED_UTC = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _wall_clock() -> datetime:
    return FIXED_UTC


# ---------------------------------------------------------------------------
# Fake transports and clocks (no real sockets, no Docker)


class FakeSleep:
    """Deterministic sleep that advances the shared monotonic clock."""

    def __init__(self, clock: Any) -> None:
        self._clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self._clock.advance(seconds)


class FakePostgresConnection:
    """Scripted stand-in for an asyncpg connection."""

    def __init__(
        self,
        *,
        value: Any = 1,
        error: BaseException | None = None,
        latency: float = 0.0,
        clock: Any = None,
    ) -> None:
        self._value = value
        self._error = error
        self._latency = latency
        self._clock = clock
        self.queries: list[str] = []
        self.closed = False
        self.terminated = False

    async def fetchval(self, query: str) -> Any:
        self.queries.append(query)
        if self._latency and self._clock is not None:
            self._clock.advance(self._latency)
        if self._error is not None:
            raise self._error
        return self._value

    async def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True


class HangingPostgresConnection:
    """A connection whose query never answers; cancellation must terminate it."""

    def __init__(self) -> None:
        self.closed = False
        self.terminated = False

    async def fetchval(self, query: str) -> Any:
        await asyncio.sleep(3600)
        return None

    async def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True


class FakePostgresConnector:
    """Queue scripted connections or errors for the asyncpg connect seam."""

    def __init__(self, clock: Any = None) -> None:
        self.calls: list[tuple[Any, float]] = []
        self._queue: deque[Any] = deque()
        self._clock = clock

    def queue_result(self, value: Any = 1, *, latency: float = 0.0) -> FakePostgresConnection:
        conn = FakePostgresConnection(value=value, latency=latency, clock=self._clock)
        self._queue.append(conn)
        return conn

    def queue_error(self, exc: BaseException) -> None:
        self._queue.append(exc)

    def queue_connection(self, conn: Any) -> None:
        self._queue.append(conn)

    async def __call__(self, target: Any, timeout: float) -> Any:
        self.calls.append((target, timeout))
        if not self._queue:
            raise AssertionError("fake postgres connector received an undeclared call")
        item = self._queue.popleft()
        if isinstance(item, BaseException):
            raise item
        return item


class FakeWriter:
    """Record written bytes; the reader counterpart is fed separately."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    @property
    def payload(self) -> bytes:
        return b"".join(self.writes)


_HANG = object()


class FakeTcpConnector:
    """Queue scripted raw responses, errors, or hangs for the TCP connect seam."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.pairs: list[tuple[asyncio.StreamReader, FakeWriter]] = []
        self._queue: deque[Any] = deque()

    def queue_response(self, data: bytes) -> None:
        self._queue.append(data)

    def queue_error(self, exc: BaseException) -> None:
        self._queue.append(exc)

    def queue_hang(self) -> None:
        self._queue.append(_HANG)

    async def __call__(self, host: str, port: int) -> tuple[asyncio.StreamReader, FakeWriter]:
        self.calls.append((host, port))
        if not self._queue:
            raise AssertionError("fake TCP connector received an undeclared call")
        item = self._queue.popleft()
        if isinstance(item, BaseException):
            raise item
        reader = asyncio.StreamReader()
        if item is not _HANG:
            reader.feed_data(item)
            reader.feed_eof()
        writer = FakeWriter()
        self.pairs.append((reader, writer))
        return reader, writer


# ---------------------------------------------------------------------------
# Protocol bytes helpers


def _resp_simple(text: str) -> bytes:
    return f"+{text}\r\n".encode("ascii")


def _resp_error(text: str) -> bytes:
    return f"-{text}\r\n".encode("ascii")


def _resp_auth_command(secret: str) -> bytes:
    encoded = secret.encode("utf-8")
    length = str(len(encoded)).encode("ascii")
    return b"*2\r\n$4\r\nAUTH\r\n$" + length + b"\r\n" + encoded + b"\r\n"


_RESP_PING_COMMAND = b"*1\r\n$4\r\nPING\r\n"


def _http_response(
    status: int, body: bytes, *, reason: str = "OK", content_length: bool = True
) -> bytes:
    head = f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
    if content_length:
        head += f"Content-Length: {len(body)}\r\n"
    return head.encode("latin-1") + b"\r\n" + body


_GRAFANA_HEALTH_OK = b'{"commit":"0123456789abcdef","database":"ok","version":"13.0.3"}'
_GRAFANA_ADMIN_OK = b'{"id":1,"email":"admin@localhost","login":"admin","isGrafanaAdmin":true}'


def _basic_header(secret: str) -> str:
    return base64.b64encode(f"admin:{secret}".encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# Target builders, runner, and shared assertions


def _postgres_target(secret: str) -> Any:
    return _probes().ProbeTarget(
        dependency=models.DependencyId.POSTGRES,
        host="127.0.0.1",
        port=15432,
        username="local_user",
        database="local_db",
        secret=secret,
    )


def _redis_target(secret: str) -> Any:
    return _probes().ProbeTarget(
        dependency=models.DependencyId.REDIS,
        host="127.0.0.1",
        port=16379,
        db_number=0,
        secret=secret,
    )


def _grafana_target(secret: str) -> Any:
    return _probes().ProbeTarget(
        dependency=models.DependencyId.GRAFANA,
        host="127.0.0.1",
        port=13000,
        secret=secret,
    )


async def _run(
    target: Any,
    clock: Any,
    *,
    budget: float = 60.0,
    attempt_timeout: float = 2.0,
    retry_interval: float = 0.5,
    postgres_connect: Any = None,
    tcp_connect: Any = None,
    sleep: Any = None,
) -> Any:
    probes = _probes()
    return await probes.probe_dependency(
        target,
        deadline=clock.now + budget,
        clock=clock,
        sleep=sleep if sleep is not None else FakeSleep(clock),
        wall_clock=_wall_clock,
        postgres_connect=postgres_connect,
        tcp_connect=tcp_connect,
        attempt_timeout=attempt_timeout,
        retry_interval=retry_interval,
    )


def _assert_ready(result: Any, *, dependency: Any, probe_kind: Any) -> None:
    assert result.dependency == dependency
    assert result.readiness == models.ReadinessState.READY
    assert result.liveness == models.LivenessState.ALIVE
    assert result.probe == probe_kind
    assert result.code == events.DiagnosticCodeV2.OK.value
    assert result.safe_reason == ""
    assert result.checked_at == FIXED_UTC
    assert result.checked_at.utcoffset() == FIXED_UTC.utcoffset()
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


def _assert_not_ready(
    result: Any,
    *,
    dependency: Any,
    outcome: Any,
    liveness: Any,
    probe_kind: Any = None,
) -> None:
    probes = _probes()
    assert result.dependency == dependency
    assert result.readiness == models.ReadinessState.NOT_READY
    assert result.liveness == liveness
    assert result.code == events.DiagnosticCodeV2.DEPENDENCY_NOT_READY.value
    assert result.safe_reason == probes.safe_reason(dependency, outcome)
    assert 0 < len(result.safe_reason) <= models.SAFE_REASON_MAX_LENGTH
    if probe_kind is not None:
        assert result.probe == probe_kind
    assert result.checked_at == FIXED_UTC
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Probe target validation


class TestProbeTargetValidation:
    def test_secret_excluded_from_repr_and_equality(self, synthetic_secret_factory: Any) -> None:
        first = synthetic_secret_factory.new()
        second = synthetic_secret_factory.new()
        target = _postgres_target(first)
        assert first not in repr(target)
        assert second not in repr(target)
        # Like ComposeSecretMaterial, secret bytes never participate in equality.
        assert target == _postgres_target(second)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"username": ""},
            {"database": ""},
            {"secret": ""},
        ],
    )
    def test_postgres_requires_user_database_secret(
        self, overrides: dict[str, str], synthetic_secret: str
    ) -> None:
        probes = _probes()
        kwargs = {
            "dependency": models.DependencyId.POSTGRES,
            "host": "127.0.0.1",
            "port": 15432,
            "username": "local_user",
            "database": "local_db",
            "secret": synthetic_secret,
        }
        kwargs.update(overrides)
        with pytest.raises(ValueError):
            probes.ProbeTarget(**kwargs)

    def test_redis_requires_secret(self) -> None:
        probes = _probes()
        with pytest.raises(ValueError):
            probes.ProbeTarget(dependency=models.DependencyId.REDIS, host="127.0.0.1", port=16379)

    def test_redis_db_number_must_be_non_negative(self, synthetic_secret: str) -> None:
        probes = _probes()
        with pytest.raises(ValueError):
            probes.ProbeTarget(
                dependency=models.DependencyId.REDIS,
                host="127.0.0.1",
                port=16379,
                db_number=-1,
                secret=synthetic_secret,
            )

    def test_grafana_requires_secret(self) -> None:
        probes = _probes()
        with pytest.raises(ValueError):
            probes.ProbeTarget(dependency=models.DependencyId.GRAFANA, host="127.0.0.1", port=13000)

    @pytest.mark.parametrize("port", [0, 65536, -1])
    def test_port_bounds(self, port: int, synthetic_secret: str) -> None:
        probes = _probes()
        with pytest.raises(ValueError):
            probes.ProbeTarget(
                dependency=models.DependencyId.REDIS,
                host="127.0.0.1",
                port=port,
                secret=synthetic_secret,
            )

    def test_host_required(self, synthetic_secret: str) -> None:
        probes = _probes()
        with pytest.raises(ValueError):
            probes.ProbeTarget(
                dependency=models.DependencyId.REDIS,
                host="",
                port=16379,
                secret=synthetic_secret,
            )


# ---------------------------------------------------------------------------
# PostgreSQL authenticated SELECT 1


class TestPostgresProbe:
    async def test_select_1_exact_one_is_ready(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        connector = FakePostgresConnector(clock=monotonic_clock)
        conn = connector.queue_result(1)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=connector,
        )
        _assert_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            probe_kind=models.ProbeKind.POSTGRES_QUERY,
        )
        assert conn.queries == ["SELECT 1"]
        assert conn.closed and not conn.terminated
        assert len(connector.calls) == 1
        _, timeout = connector.calls[0]
        assert timeout == 2.0  # min(attempt_timeout, remaining budget)

    @pytest.mark.parametrize("bad", [0, 2, "1", 1.0, None, True])
    async def test_wrong_result_is_rejected(
        self, bad: Any, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        for _ in range(4):
            connector.queue_result(bad)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            postgres_connect=connector,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.UNEXPECTED_RESPONSE,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.POSTGRES_QUERY,
        )
        # Exact truncation by remaining time: 1.0, then 0.6, then 0.2; never extended.
        assert [timeout for _, timeout in connector.calls] == pytest.approx([1.0, 0.6, 0.2])
        assert monotonic_clock.now == pytest.approx(1001.0)  # deadline, never exceeded

    async def test_auth_failure_is_unretryable(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        connector.queue_error(
            asyncpg.InvalidPasswordError(f"password authentication failed: {synthetic_secret}")
        )
        sleep = FakeSleep(monotonic_clock)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            postgres_connect=connector,
            sleep=sleep,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.ALIVE,
        )
        assert len(connector.calls) == 1
        assert sleep.calls == []
        assert synthetic_secret not in result.safe_reason

    async def test_missing_database_is_unretryable(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        connector.queue_error(asyncpg.InvalidCatalogNameError("database does not exist"))
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            postgres_connect=connector,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.ALIVE,
        )
        assert len(connector.calls) == 1

    async def test_connection_refused_retries_until_deadline(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        for _ in range(4):
            connector.queue_error(
                ConnectionRefusedError(f"refused for password {synthetic_secret}")
            )
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            postgres_connect=connector,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.CONNECT_FAILED,
            liveness=models.LivenessState.NOT_ALIVE,
        )
        assert len(connector.calls) == 3
        assert synthetic_secret not in result.safe_reason

    async def test_starting_server_retries_then_recovers(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        connector = FakePostgresConnector(clock=monotonic_clock)
        connector.queue_error(asyncpg.CannotConnectNowError("the database system is starting up"))
        fresh = connector.queue_result(1)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=connector,
        )
        _assert_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            probe_kind=models.ProbeKind.POSTGRES_QUERY,
        )
        # Fresh evidence: the recovery ran on a brand-new connection.
        assert len(connector.calls) == 2
        assert fresh.queries == ["SELECT 1"]

    async def test_stale_attempt_result_is_superseded(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        connector = FakePostgresConnector(clock=monotonic_clock)
        connector.queue_result(2)  # earlier wrong answer must not decide the probe
        connector.queue_result(1)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=connector,
        )
        _assert_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            probe_kind=models.ProbeKind.POSTGRES_QUERY,
        )
        assert len(connector.calls) == 2

    async def test_post_deadline_success_is_rejected(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        # The query consumes 5 fake seconds, landing after the 1-second deadline.
        connector.queue_result(1, latency=5.0)
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=2.0,
            postgres_connect=connector,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.TIMEOUT,
            liveness=models.LivenessState.UNKNOWN,
        )

    async def test_hanging_attempt_is_cancelled_and_terminated(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        connector = FakePostgresConnector(clock=monotonic_clock)
        hanging = HangingPostgresConnection()
        connector.queue_connection(hanging)
        connector.queue_connection(HangingPostgresConnection())
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=0.1,
            attempt_timeout=0.05,
            retry_interval=0.05,
            postgres_connect=connector,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.POSTGRES,
            outcome=probes.ProbeOutcome.TIMEOUT,
            liveness=models.LivenessState.UNKNOWN,
        )
        assert hanging.terminated

    async def test_failure_then_recovery_reports_latest_state(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        failing = FakePostgresConnector(clock=monotonic_clock)
        for _ in range(4):
            failing.queue_error(ConnectionRefusedError("refused"))
        first = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            postgres_connect=failing,
        )
        assert first.readiness == models.ReadinessState.NOT_READY

        recovering = FakePostgresConnector(clock=monotonic_clock)
        recovering.queue_result(1)
        second = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=recovering,
        )
        _assert_ready(
            second,
            dependency=models.DependencyId.POSTGRES,
            probe_kind=models.ProbeKind.POSTGRES_QUERY,
        )

    async def test_recovery_then_failure_reports_latest_state(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        healthy = FakePostgresConnector(clock=monotonic_clock)
        healthy.queue_result(1)
        first = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=healthy,
        )
        assert first.readiness == models.ReadinessState.READY

        failing = FakePostgresConnector(clock=monotonic_clock)
        failing.queue_error(asyncpg.InvalidPasswordError("password authentication failed"))
        second = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            postgres_connect=failing,
        )
        assert second.readiness == models.ReadinessState.NOT_READY
        assert second.code == events.DiagnosticCodeV2.DEPENDENCY_NOT_READY.value


# ---------------------------------------------------------------------------
# Redis AUTH/PING on one connection


class TestRedisProbe:
    async def test_auth_then_ping_on_one_connection(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        tcp.queue_response(_resp_simple("OK") + _resp_simple("PONG"))
        result = await _run(_redis_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.REDIS,
            probe_kind=models.ProbeKind.REDIS_AUTH_PING,
        )
        assert tcp.calls == [("127.0.0.1", 16379)]
        assert len(tcp.pairs) == 1
        _, writer = tcp.pairs[0]
        assert writer.payload == _resp_auth_command(synthetic_secret) + _RESP_PING_COMMAND
        assert writer.closed

    async def test_ping_requires_pong(self, monotonic_clock: Any, synthetic_secret: str) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_response(_resp_simple("OK") + _resp_simple("OK"))
        result = await _run(
            _redis_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.UNEXPECTED_RESPONSE,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.REDIS_AUTH_PING,
        )
        assert len(tcp.calls) == 3

    async def test_cross_connection_evidence_never_counts(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        # First connection answers AUTH but drops before PONG; only the second
        # connection carries a PONG, and only after its own fresh AUTH.
        tcp.queue_response(_resp_simple("OK"))
        tcp.queue_response(_resp_simple("OK") + _resp_simple("PONG"))
        result = await _run(_redis_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.REDIS,
            probe_kind=models.ProbeKind.REDIS_AUTH_PING,
        )
        assert len(tcp.pairs) == 2
        for _, writer in tcp.pairs:
            assert writer.payload == (_resp_auth_command(synthetic_secret) + _RESP_PING_COMMAND)

    async def test_auth_failure_is_unretryable(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        tcp.queue_response(_resp_error("WRPASS invalid username-password pair"))
        sleep = FakeSleep(monotonic_clock)
        result = await _run(
            _redis_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            tcp_connect=tcp,
            sleep=sleep,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.ALIVE,
        )
        assert len(tcp.calls) == 1
        assert sleep.calls == []

    async def test_loading_error_is_retryable_then_recovers(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        tcp.queue_response(_resp_error("LOADING Redis is loading the dataset in memory"))
        tcp.queue_response(_resp_simple("OK") + _resp_simple("PONG"))
        result = await _run(_redis_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.REDIS,
            probe_kind=models.ProbeKind.REDIS_AUTH_PING,
        )
        assert len(tcp.pairs) == 2

    async def test_eof_during_auth_maps_to_connect_failure(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_response(b"")
        result = await _run(
            _redis_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.CONNECT_FAILED,
            liveness=models.LivenessState.NOT_ALIVE,
        )
        assert len(tcp.calls) == 3

    async def test_connection_refused_maps_to_connect_failure(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_error(ConnectionRefusedError(f"refused: {synthetic_secret}"))
        result = await _run(
            _redis_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.CONNECT_FAILED,
            liveness=models.LivenessState.NOT_ALIVE,
        )
        assert synthetic_secret not in result.safe_reason

    async def test_hanging_reply_is_cancelled_and_closed(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        tcp.queue_hang()
        tcp.queue_hang()
        result = await _run(
            _redis_target(synthetic_secret),
            monotonic_clock,
            budget=0.1,
            attempt_timeout=0.05,
            retry_interval=0.05,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.TIMEOUT,
            liveness=models.LivenessState.UNKNOWN,
        )
        assert tcp.pairs[0][1].closed

    async def test_secret_with_control_characters_never_serialized(
        self, monotonic_clock: Any
    ) -> None:
        probes = _probes()
        injected = "tm_local_" + "A" * 16 + "\r\nFLUSHALL"
        tcp = FakeTcpConnector()
        result = await _run(_redis_target(injected), monotonic_clock, tcp_connect=tcp)
        _assert_not_ready(
            result,
            dependency=models.DependencyId.REDIS,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.UNKNOWN,
        )
        # The payload must fail closed before any network access.
        assert tcp.calls == []
        assert "FLUSHALL" not in result.safe_reason


# ---------------------------------------------------------------------------
# Grafana health database plus administrator identity


class TestGrafanaProbe:
    async def test_health_and_admin_identity_ready(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        tcp.queue_response(_http_response(200, _GRAFANA_ADMIN_OK))
        result = await _run(_grafana_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            probe_kind=models.ProbeKind.GRAFANA_ADMIN,
        )
        assert tcp.calls == [("127.0.0.1", 13000), ("127.0.0.1", 13000)]
        health_request = tcp.pairs[0][1].payload.decode("latin-1")
        admin_request = tcp.pairs[1][1].payload.decode("latin-1")
        assert health_request.startswith("GET /api/health HTTP/1.1\r\n")
        assert "Host: 127.0.0.1:13000\r\n" in health_request
        assert "Authorization" not in health_request
        assert synthetic_secret not in health_request
        assert "Connection: close\r\n" in health_request
        assert admin_request.startswith("GET /api/user HTTP/1.1\r\n")
        assert f"Authorization: Basic {_basic_header(synthetic_secret)}\r\n" in admin_request
        assert "Connection: close\r\n" in admin_request

    async def test_health_database_not_ok_is_unexpected(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_response(_http_response(200, b'{"database":"migrating"}'))
        result = await _run(
            _grafana_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            outcome=probes.ProbeOutcome.UNEXPECTED_RESPONSE,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.GRAFANA_HEALTH,
        )
        assert len(tcp.calls) == 3

    async def test_health_non_200_is_unexpected(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_response(
                _http_response(503, b'{"message":"unavailable"}', reason="Service Unavailable")
            )
        result = await _run(
            _grafana_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            outcome=probes.ProbeOutcome.UNEXPECTED_RESPONSE,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.GRAFANA_HEALTH,
        )

    async def test_health_unparseable_body_is_unexpected(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        for _ in range(4):
            tcp.queue_response(_http_response(200, b"not-json{"))
        result = await _run(
            _grafana_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            outcome=probes.ProbeOutcome.UNEXPECTED_RESPONSE,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.GRAFANA_HEALTH,
        )

    async def test_admin_unauthorized_is_unretryable(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        tcp.queue_response(
            _http_response(
                401,
                b'{"message":"invalid username or password"}',
                reason="Unauthorized",
            )
        )
        sleep = FakeSleep(monotonic_clock)
        result = await _run(
            _grafana_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            tcp_connect=tcp,
            sleep=sleep,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.GRAFANA_ADMIN,
        )
        assert len(tcp.calls) == 2
        assert sleep.calls == []

    async def test_admin_identity_false_is_unretryable(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        tcp = FakeTcpConnector()
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        tcp.queue_response(_http_response(200, b'{"id":2,"login":"admin","isGrafanaAdmin":false}'))
        result = await _run(
            _grafana_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            outcome=probes.ProbeOutcome.AUTH_FAILED,
            liveness=models.LivenessState.ALIVE,
            probe_kind=models.ProbeKind.GRAFANA_ADMIN,
        )
        assert len(tcp.calls) == 2

    async def test_admin_connect_failure_retries_with_fresh_health(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        tcp.queue_error(ConnectionRefusedError("refused"))
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        tcp.queue_response(_http_response(200, _GRAFANA_ADMIN_OK))
        result = await _run(_grafana_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            probe_kind=models.ProbeKind.GRAFANA_ADMIN,
        )
        # Every attempt re-verifies health before the admin identity check.
        assert len(tcp.calls) == 4

    async def test_response_without_content_length_reads_to_eof(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK, content_length=False))
        tcp.queue_response(_http_response(200, _GRAFANA_ADMIN_OK, content_length=False))
        result = await _run(_grafana_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        _assert_ready(
            result,
            dependency=models.DependencyId.GRAFANA,
            probe_kind=models.ProbeKind.GRAFANA_ADMIN,
        )


# ---------------------------------------------------------------------------
# Shared-deadline truncation


class TestDeadlineTruncation:
    @pytest.mark.parametrize("target_builder", [_postgres_target, _redis_target, _grafana_target])
    async def test_zero_remaining_reports_timeout_without_network(
        self, target_builder: Any, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        pg = FakePostgresConnector(clock=monotonic_clock)
        tcp = FakeTcpConnector()
        target = target_builder(synthetic_secret)
        result = await probes.probe_dependency(
            target,
            deadline=monotonic_clock.now,
            clock=monotonic_clock,
            sleep=FakeSleep(monotonic_clock),
            wall_clock=_wall_clock,
            postgres_connect=pg,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=target.dependency,
            outcome=probes.ProbeOutcome.TIMEOUT,
            liveness=models.LivenessState.UNKNOWN,
        )
        assert pg.calls == []
        assert tcp.calls == []
        assert result.duration_ms == 0

    @pytest.mark.parametrize("target_builder", [_postgres_target, _redis_target, _grafana_target])
    async def test_past_deadline_reports_timeout_without_network(
        self, target_builder: Any, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        pg = FakePostgresConnector(clock=monotonic_clock)
        tcp = FakeTcpConnector()
        target = target_builder(synthetic_secret)
        result = await probes.probe_dependency(
            target,
            deadline=monotonic_clock.now - 10.0,
            clock=monotonic_clock,
            sleep=FakeSleep(monotonic_clock),
            wall_clock=_wall_clock,
            postgres_connect=pg,
            tcp_connect=tcp,
        )
        _assert_not_ready(
            result,
            dependency=target.dependency,
            outcome=probes.ProbeOutcome.TIMEOUT,
            liveness=models.LivenessState.UNKNOWN,
        )
        assert pg.calls == []
        assert tcp.calls == []

    async def test_no_second_budget_after_deadline(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        connector = FakePostgresConnector(clock=monotonic_clock)
        for _ in range(4):
            connector.queue_result(2)
        sleep = FakeSleep(monotonic_clock)
        await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=1.0,
            attempt_timeout=5.0,
            retry_interval=0.4,
            postgres_connect=connector,
            sleep=sleep,
        )
        # Attempts plus sleeps consume exactly the budget; nothing extends it.
        assert monotonic_clock.now == pytest.approx(1001.0)
        assert sum(sleep.calls) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Safe diagnostic mapping and redaction


class TestSafeDiagnosticMapping:
    async def test_exception_details_never_leak(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        probes = _probes()
        poisonous = (
            f"postgresql://local_user:{synthetic_secret}@127.0.0.1:15432/local_db "
            f"refused; trace at /Users/developer/Projects/TokenMarket/x.py; "
            f"password={synthetic_secret}"
        )
        connector = FakePostgresConnector(clock=monotonic_clock)
        connector.queue_error(OSError(poisonous))
        result = await _run(
            _postgres_target(synthetic_secret),
            monotonic_clock,
            budget=0.2,
            attempt_timeout=1.0,
            retry_interval=0.2,
            postgres_connect=connector,
        )
        blob = repr(result) + result.safe_reason + result.code
        assert synthetic_secret not in blob
        assert "/Users/" not in blob
        assert "password=" not in blob
        assert "postgresql://" not in blob
        assert result.safe_reason == probes.safe_reason(
            models.DependencyId.POSTGRES, probes.ProbeOutcome.CONNECT_FAILED
        )
        assert len(result.safe_reason) <= models.SAFE_REASON_MAX_LENGTH

    async def test_grafana_raw_body_and_error_never_leak(
        self, monotonic_clock: Any, synthetic_secret: str
    ) -> None:
        tcp = FakeTcpConnector()
        health_with_secret = b'{"database":"ok","debug":"' + synthetic_secret.encode() + b'"}'
        denied_with_secret = (
            b'{"message":"denied ' + synthetic_secret.encode() + b' from /tmp/trace"}'
        )
        tcp.queue_response(_http_response(200, health_with_secret))
        tcp.queue_response(_http_response(401, denied_with_secret, reason="Unauthorized"))
        result = await _run(_grafana_target(synthetic_secret), monotonic_clock, tcp_connect=tcp)
        blob = repr(result) + result.safe_reason + result.code
        assert synthetic_secret not in blob
        assert "/tmp/" not in blob
        assert "denied" not in blob

    def test_failure_codes_are_stable_v2_codes(self) -> None:
        probes = _probes()
        stable = events.stable_codes_v2()
        assert events.DiagnosticCodeV2.OK.value in stable
        assert events.DiagnosticCodeV2.DEPENDENCY_NOT_READY.value in stable
        for dependency in models.DependencyId:
            for outcome in probes.ProbeOutcome:
                reason = probes.safe_reason(dependency, outcome)
                assert len(reason) <= models.SAFE_REASON_MAX_LENGTH


# ---------------------------------------------------------------------------
# Independent, concurrently schedulable probes


class TestProbeIndependence:
    async def test_three_probes_run_concurrently_without_depends_on(
        self, monotonic_clock: Any, synthetic_secret_factory: Any
    ) -> None:
        probes = _probes()
        pg = FakePostgresConnector(clock=monotonic_clock)
        pg.queue_result(1)
        redis_tcp = FakeTcpConnector()
        redis_tcp.queue_response(_resp_simple("OK") + _resp_simple("PONG"))
        grafana_tcp = FakeTcpConnector()
        grafana_tcp.queue_response(_http_response(200, _GRAFANA_HEALTH_OK))
        grafana_tcp.queue_response(_http_response(200, _GRAFANA_ADMIN_OK))

        deadline = monotonic_clock.now + 60.0

        async def _one(target: Any, **seams: Any) -> Any:
            return await probes.probe_dependency(
                target,
                deadline=deadline,
                clock=monotonic_clock,
                sleep=FakeSleep(monotonic_clock),
                wall_clock=_wall_clock,
                **seams,
            )

        results = await asyncio.gather(
            _one(_postgres_target(synthetic_secret_factory.new()), postgres_connect=pg),
            _one(_redis_target(synthetic_secret_factory.new()), tcp_connect=redis_tcp),
            _one(_grafana_target(synthetic_secret_factory.new()), tcp_connect=grafana_tcp),
        )
        assert [result.dependency for result in results] == [
            models.DependencyId.POSTGRES,
            models.DependencyId.REDIS,
            models.DependencyId.GRAFANA,
        ]
        for result in results:
            assert result.readiness == models.ReadinessState.READY
            assert result.code == events.DiagnosticCodeV2.OK.value
