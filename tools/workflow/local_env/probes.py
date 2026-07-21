"""Bounded authenticated readiness probes for the SF02 local dependencies (T029).

Implements research Decision 10 and the readiness contract of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
using only the locked ``asyncpg`` dependency and the standard library:

- PostgreSQL: authenticate over TCP with the configured user/password/database
  and require ``SELECT 1`` to return exactly ``1`` (asyncpg).
- Redis: minimal RESP over ``asyncio.open_connection`` — AUTH with the URL
  password, then PING on the *same* connection, requiring exactly ``PONG``.
  Evidence from any other connection or earlier attempt is stale and rejected.
- Grafana: HTTP/1.1 over ``asyncio.open_connection`` — unauthenticated
  ``GET /api/health`` must be 200 with ``database == "ok"`` AND Basic-auth
  ``GET /api/user`` must be 200 with ``isGrafanaAdmin == true``.

Every probe shares one caller-owned monotonic deadline: each attempt is bounded
by ``min(attempt_timeout, deadline - monotonic_now)`` with exact truncation (no
second budget, no extension), and when no time remains the stable timeout
category is reported without any network access. Authentication/identity
failures are unretryable; connection, timeout, and unexpected responses retry
at a short fixed interval until the deadline. Every attempt opens fresh
connections, so the latest state always wins in both recovery directions. Raw
health output, HTTP bodies, exception text, URLs with user-info, secrets, and
absolute paths never surface: outcomes map to the stable v2 codes ``OK`` /
``DEPENDENCY_NOT_READY`` with bounded static reasons. The three probes are
independent and concurrently schedulable (no ``depends_on``).
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

# The locked asyncpg 0.30.x ships no py.typed marker; the reviewed lockfile
# forbids adding stub packages here, so the ignore stays on this one import and
# the connector seam below narrows the call site to a typed local.
import asyncpg  # type: ignore[import-untyped]

from ..events import DiagnosticCodeV2
from .models import DependencyHealthResult, DependencyId, LivenessState, ProbeKind, ReadinessState

ATTEMPT_TIMEOUT_SECONDS = 2.0
RETRY_INTERVAL_SECONDS = 0.5
GRAFANA_ADMIN_USERNAME = "admin"

# Monotonic arithmetic is floating point: after a sleep that consumed the
# exact remainder, `deadline - clock()` can stay positive by ~1e-13. A
# sub-microsecond remainder cannot perform any I/O, so it is treated as
# exhausted. This never extends the budget or adds a second one.
_MIN_ATTEMPT_BUDGET_SECONDS = 1e-6

ClockFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]
WallClockFn = Callable[[], datetime]

__all__ = [
    "ATTEMPT_TIMEOUT_SECONDS",
    "GRAFANA_ADMIN_USERNAME",
    "RETRY_INTERVAL_SECONDS",
    "ClockFn",
    "PostgresConnectFn",
    "PostgresConnectionLike",
    "ProbeOutcome",
    "ProbeTarget",
    "SleepFn",
    "StreamReaderLike",
    "StreamWriterLike",
    "TcpConnectFn",
    "WallClockFn",
    "probe_dependency",
    "safe_reason",
]


class ProbeOutcome(str, Enum):
    """Stable redacted probe categories; only the reason string is serialized."""

    READY = "ready"
    AUTH_FAILED = "auth-failed"
    CONNECT_FAILED = "connect-failed"
    TIMEOUT = "timeout"
    UNEXPECTED_RESPONSE = "unexpected-response"


@dataclass(frozen=True)
class ProbeTarget:
    """In-memory probe input projected from validated connection facts.

    ``secret`` bytes are excluded from repr and equality so they can never
    leak into diagnostics; the projection itself is never serialized.
    """

    dependency: DependencyId
    host: str
    port: int
    username: str = ""
    database: str = ""
    db_number: int = 0
    secret: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("probe target host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("probe target port must be within 1..65535")
        if self.dependency is DependencyId.POSTGRES:
            if not self.username:
                raise ValueError("postgres probe target requires a username")
            if not self.database:
                raise ValueError("postgres probe target requires a database")
            if not self.secret:
                raise ValueError("postgres probe target requires a password secret")
        elif self.dependency is DependencyId.REDIS:
            if not self.secret:
                raise ValueError("redis probe target requires a password secret")
            if self.db_number < 0:
                raise ValueError("redis probe target db number must be non-negative")
        elif self.dependency is DependencyId.GRAFANA:
            if not self.secret:
                raise ValueError("grafana probe target requires an admin password secret")


# ---------------------------------------------------------------------------
# Injected transport seams (the real defaults stay dependency-free)


class PostgresConnectionLike(Protocol):
    """The subset of ``asyncpg.Connection`` a probe uses."""

    async def fetchval(self, query: str) -> Any: ...

    async def close(self) -> None: ...

    def terminate(self) -> None: ...


PostgresConnectFn = Callable[[ProbeTarget, float], Awaitable[PostgresConnectionLike]]


class StreamReaderLike(Protocol):
    """The subset of ``asyncio.StreamReader`` the RESP/HTTP probes use."""

    async def readuntil(self, separator: bytes = b"\n") -> bytes: ...

    async def readexactly(self, n: int) -> bytes: ...

    async def read(self, n: int = -1) -> bytes: ...


class StreamWriterLike(Protocol):
    """The subset of ``asyncio.StreamWriter`` the RESP/HTTP probes use."""

    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...

    def close(self) -> None: ...

    async def wait_closed(self) -> None: ...


TcpConnectFn = Callable[[str, int], Awaitable[tuple[StreamReaderLike, StreamWriterLike]]]


async def _asyncpg_connect(target: ProbeTarget, timeout: float) -> PostgresConnectionLike:
    """Open one real PostgreSQL connection with the derived host facts."""
    connection: PostgresConnectionLike = await asyncpg.connect(
        host=target.host,
        port=target.port,
        user=target.username,
        password=target.secret,
        database=target.database,
        timeout=timeout,
    )
    return connection


async def _asyncio_open_connection(
    host: str, port: int
) -> tuple[StreamReaderLike, StreamWriterLike]:
    """Open one real TCP connection through the standard library."""
    reader, writer = await asyncio.open_connection(host, port)
    return reader, writer


# ---------------------------------------------------------------------------
# Safe diagnostic categories


class _ProtocolViolation(Exception):
    """A peer (or local serializer input) violated the expected protocol shape."""


_AUTH_REASONS: Mapping[DependencyId, str] = {
    DependencyId.POSTGRES: (
        "postgres rejected the configured user, password, or database; "
        "fix DATABASE_URL and retry"
    ),
    DependencyId.REDIS: "redis rejected the configured password; fix REDIS_URL and retry",
    DependencyId.GRAFANA: (
        "grafana administrator credentials or identity were rejected; "
        "fix GRAFANA_ADMIN_PASSWORD and retry"
    ),
}

_LIVENESS: Mapping[ProbeOutcome, LivenessState] = {
    ProbeOutcome.READY: LivenessState.ALIVE,
    ProbeOutcome.AUTH_FAILED: LivenessState.ALIVE,
    ProbeOutcome.CONNECT_FAILED: LivenessState.NOT_ALIVE,
    ProbeOutcome.TIMEOUT: LivenessState.UNKNOWN,
    ProbeOutcome.UNEXPECTED_RESPONSE: LivenessState.ALIVE,
}

_FIRST_STAGE_KIND: Mapping[DependencyId, ProbeKind] = {
    DependencyId.POSTGRES: ProbeKind.POSTGRES_QUERY,
    DependencyId.REDIS: ProbeKind.REDIS_AUTH_PING,
    DependencyId.GRAFANA: ProbeKind.GRAFANA_HEALTH,
}

_UNRETRYABLE = frozenset({ProbeOutcome.AUTH_FAILED})


def safe_reason(dependency: DependencyId, outcome: ProbeOutcome) -> str:
    """Bounded static reason for one outcome; never raw output or values."""
    if outcome is ProbeOutcome.READY:
        return ""
    if outcome is ProbeOutcome.AUTH_FAILED:
        return _AUTH_REASONS[dependency]
    name = dependency.value
    if outcome is ProbeOutcome.CONNECT_FAILED:
        return (
            f"{name} connection failed or was dropped before the probe "
            "completed; check the dependency and retry"
        )
    if outcome is ProbeOutcome.TIMEOUT:
        return (
            f"{name} probe did not complete within the shared readiness "
            "deadline; inspect the dependency and retry"
        )
    return (
        f"{name} returned an unexpected response to the readiness probe; "
        "inspect the dependency and retry"
    )


@dataclass(frozen=True)
class _AttemptOutcome:
    """One fresh attempt's category plus the evidence stage it came from."""

    kind: ProbeOutcome
    probe_kind: ProbeKind
    liveness: LivenessState | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# PostgreSQL authenticated SELECT 1


async def _postgres_attempt(
    target: ProbeTarget, timeout: float, connect: PostgresConnectFn
) -> _AttemptOutcome:
    conn: PostgresConnectionLike | None = None
    outcome: _AttemptOutcome
    try:
        conn = await connect(target, timeout)
        value: Any = await conn.fetchval("SELECT 1")
        if type(value) is int and value == 1:
            outcome = _AttemptOutcome(ProbeOutcome.READY, ProbeKind.POSTGRES_QUERY)
        else:
            outcome = _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.POSTGRES_QUERY)
    except asyncio.CancelledError:
        if conn is not None:
            conn.terminate()
        raise
    except (
        asyncpg.InvalidAuthorizationSpecificationError,
        asyncpg.InvalidCatalogNameError,
    ):
        # Credentials or the configured database were rejected; retrying the
        # same facts cannot succeed, so this category is unretryable.
        outcome = _AttemptOutcome(ProbeOutcome.AUTH_FAILED, ProbeKind.POSTGRES_QUERY)
    except asyncpg.CannotConnectNowError:
        outcome = _AttemptOutcome(ProbeOutcome.CONNECT_FAILED, ProbeKind.POSTGRES_QUERY)
    except TimeoutError:
        outcome = _AttemptOutcome(ProbeOutcome.TIMEOUT, ProbeKind.POSTGRES_QUERY)
    except OSError:
        outcome = _AttemptOutcome(ProbeOutcome.CONNECT_FAILED, ProbeKind.POSTGRES_QUERY)
    except Exception:
        outcome = _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.POSTGRES_QUERY)
    if conn is not None:
        try:
            await conn.close()
        except Exception:
            pass
    return outcome


# ---------------------------------------------------------------------------
# Redis RESP AUTH + PING on one connection


def _resp_command(*parts: str) -> bytes:
    """Serialize one RESP command array, refusing control-character injection."""
    chunks = [f"*{len(parts)}\r\n".encode("ascii")]
    for part in parts:
        encoded = part.encode("utf-8")
        if b"\r" in encoded or b"\n" in encoded:
            raise _ProtocolViolation("probe argument contains RESP control characters")
        chunks.append(f"${len(encoded)}\r\n".encode("ascii"))
        chunks.append(encoded + b"\r\n")
    return b"".join(chunks)


async def _read_resp_reply(reader: StreamReaderLike) -> tuple[bytes, bytes]:
    """Read one RESP reply as a ``(prefix, payload)`` pair; no output survives."""
    line = await reader.readuntil(b"\r\n")
    if len(line) < 3 or not line.endswith(b"\r\n"):
        raise _ProtocolViolation("malformed RESP reply line")
    prefix, payload = line[:1], line[1:-2]
    if prefix == b"$":
        length = int(payload)
        if length < 0:
            return (prefix, b"")
        data = await reader.readexactly(length + 2)
        return (prefix, data[:-2])
    if prefix == b"*":
        raise _ProtocolViolation("unexpected RESP aggregate reply")
    return (prefix, payload)


async def _redis_attempt(
    target: ProbeTarget, timeout: float, connect: TcpConnectFn
) -> _AttemptOutcome:
    # Serialize AUTH first: a grammar violation fails closed before any
    # network access, so an injection payload is never put on the wire.
    try:
        auth_command = _resp_command("AUTH", target.secret)
    except _ProtocolViolation:
        return _AttemptOutcome(
            ProbeOutcome.AUTH_FAILED,
            ProbeKind.REDIS_AUTH_PING,
            LivenessState.UNKNOWN,
        )
    ping_command = _resp_command("PING")
    writer: StreamWriterLike | None = None
    outcome: _AttemptOutcome
    try:
        reader, writer = await connect(target.host, target.port)
        writer.write(auth_command)
        await writer.drain()
        auth_reply = await _read_resp_reply(reader)
        if auth_reply[0] == b"-":
            text = auth_reply[1].decode("utf-8", errors="replace")
            if text.startswith("LOADING"):
                outcome = _AttemptOutcome(
                    ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.REDIS_AUTH_PING
                )
            else:
                outcome = _AttemptOutcome(ProbeOutcome.AUTH_FAILED, ProbeKind.REDIS_AUTH_PING)
        elif auth_reply != (b"+", b"OK"):
            outcome = _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.REDIS_AUTH_PING)
        else:
            # AUTH succeeded on this connection; PING must use the same one.
            writer.write(ping_command)
            await writer.drain()
            ping_reply = await _read_resp_reply(reader)
            if ping_reply == (b"+", b"PONG"):
                outcome = _AttemptOutcome(ProbeOutcome.READY, ProbeKind.REDIS_AUTH_PING)
            else:
                outcome = _AttemptOutcome(
                    ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.REDIS_AUTH_PING
                )
    except asyncio.CancelledError:
        if writer is not None:
            writer.close()
        raise
    except TimeoutError:
        outcome = _AttemptOutcome(ProbeOutcome.TIMEOUT, ProbeKind.REDIS_AUTH_PING)
    except (OSError, asyncio.IncompleteReadError):
        outcome = _AttemptOutcome(ProbeOutcome.CONNECT_FAILED, ProbeKind.REDIS_AUTH_PING)
    except Exception:
        outcome = _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.REDIS_AUTH_PING)
    if writer is not None:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    return outcome


# ---------------------------------------------------------------------------
# Grafana HTTP health plus administrator identity


def _build_request(host: str, port: int, path: str, authorization: str | None) -> bytes:
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}:{port}",
        "Accept: application/json",
        "Connection: close",
    ]
    if authorization is not None:
        lines.append(f"Authorization: {authorization}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def _parse_status_line(line: bytes) -> int:
    parts = line.split(b" ", 2)
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
        raise _ProtocolViolation("malformed HTTP status line")
    try:
        return int(parts[1])
    except ValueError as exc:
        raise _ProtocolViolation("malformed HTTP status code") from exc


async def _read_headers(reader: StreamReaderLike) -> dict[str, str]:
    headers: dict[str, str] = {}
    while True:
        line = await reader.readuntil(b"\r\n")
        if line == b"\r\n":
            return headers
        name, separator, value = line.partition(b":")
        if not separator:
            raise _ProtocolViolation("malformed HTTP header line")
        headers[name.strip().decode("latin-1").lower()] = value.strip().decode("latin-1")


async def _http_get(
    connect: TcpConnectFn,
    host: str,
    port: int,
    path: str,
    *,
    authorization: str | None,
) -> tuple[int, bytes]:
    """One bounded HTTP/1.1 GET on a fresh connection closed after the body."""
    reader, writer = await connect(host, port)
    try:
        writer.write(_build_request(host, port, path, authorization))
        await writer.drain()
        status = _parse_status_line(await reader.readuntil(b"\r\n"))
        headers = await _read_headers(reader)
        if "content-length" in headers:
            length = int(headers["content-length"])
            if length < 0:
                raise _ProtocolViolation("negative HTTP content length")
            body = await reader.readexactly(length)
        else:
            # No declared length: the peer closes after the response body.
            body = await reader.read()
    except asyncio.CancelledError:
        writer.close()
        raise
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return status, body


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        data: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _ProtocolViolation("response body is not valid JSON") from exc
    if not isinstance(data, dict):
        raise _ProtocolViolation("response body is not a JSON object")
    return data


async def _grafana_attempt(
    target: ProbeTarget, timeout: float, connect: TcpConnectFn
) -> _AttemptOutcome:
    try:
        status, body = await _http_get(
            connect, target.host, target.port, "/api/health", authorization=None
        )
        if status != 200:
            return _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.GRAFANA_HEALTH)
        if _json_object(body).get("database") != "ok":
            return _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.GRAFANA_HEALTH)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        return _AttemptOutcome(ProbeOutcome.TIMEOUT, ProbeKind.GRAFANA_HEALTH)
    except (OSError, asyncio.IncompleteReadError):
        return _AttemptOutcome(ProbeOutcome.CONNECT_FAILED, ProbeKind.GRAFANA_HEALTH)
    except Exception:
        return _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.GRAFANA_HEALTH)

    credentials = base64.b64encode(
        f"{GRAFANA_ADMIN_USERNAME}:{target.secret}".encode("utf-8")
    ).decode("ascii")
    try:
        status, body = await _http_get(
            connect,
            target.host,
            target.port,
            "/api/user",
            authorization=f"Basic {credentials}",
        )
        if status in (401, 403):
            return _AttemptOutcome(ProbeOutcome.AUTH_FAILED, ProbeKind.GRAFANA_ADMIN)
        if status != 200:
            return _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.GRAFANA_ADMIN)
        if _json_object(body).get("isGrafanaAdmin") is not True:
            # A non-admin identity is a deterministic configuration failure.
            return _AttemptOutcome(ProbeOutcome.AUTH_FAILED, ProbeKind.GRAFANA_ADMIN)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        return _AttemptOutcome(ProbeOutcome.TIMEOUT, ProbeKind.GRAFANA_ADMIN)
    except (OSError, asyncio.IncompleteReadError):
        return _AttemptOutcome(ProbeOutcome.CONNECT_FAILED, ProbeKind.GRAFANA_ADMIN)
    except Exception:
        return _AttemptOutcome(ProbeOutcome.UNEXPECTED_RESPONSE, ProbeKind.GRAFANA_ADMIN)
    return _AttemptOutcome(ProbeOutcome.READY, ProbeKind.GRAFANA_ADMIN)


# ---------------------------------------------------------------------------
# Deadline-aware bounded retry


def _timeout_outcome(target: ProbeTarget) -> _AttemptOutcome:
    return _AttemptOutcome(ProbeOutcome.TIMEOUT, _FIRST_STAGE_KIND[target.dependency])


def _attempt_fn(
    target: ProbeTarget,
    *,
    postgres_connect: PostgresConnectFn | None,
    tcp_connect: TcpConnectFn | None,
) -> Callable[[ProbeTarget, float], Awaitable[_AttemptOutcome]]:
    if target.dependency is DependencyId.POSTGRES:
        connect = postgres_connect if postgres_connect is not None else _asyncpg_connect

        async def _postgres(t: ProbeTarget, timeout: float) -> _AttemptOutcome:
            return await _postgres_attempt(t, timeout, connect)

        return _postgres

    open_connection = tcp_connect if tcp_connect is not None else _asyncio_open_connection
    if target.dependency is DependencyId.REDIS:

        async def _redis(t: ProbeTarget, timeout: float) -> _AttemptOutcome:
            return await _redis_attempt(t, timeout, open_connection)

        return _redis

    async def _grafana(t: ProbeTarget, timeout: float) -> _AttemptOutcome:
        return await _grafana_attempt(t, timeout, open_connection)

    return _grafana


def _to_result(
    target: ProbeTarget,
    outcome: _AttemptOutcome,
    wall_clock: WallClockFn,
    started: float,
    clock: ClockFn,
) -> DependencyHealthResult:
    ready = outcome.kind is ProbeOutcome.READY
    liveness = outcome.liveness if outcome.liveness is not None else _LIVENESS[outcome.kind]
    return DependencyHealthResult(
        dependency=target.dependency,
        liveness=liveness,
        readiness=ReadinessState.READY if ready else ReadinessState.NOT_READY,
        probe=outcome.probe_kind,
        checked_at=wall_clock(),
        duration_ms=max(0, int(round((clock() - started) * 1000))),
        code=(DiagnosticCodeV2.OK.value if ready else DiagnosticCodeV2.DEPENDENCY_NOT_READY.value),
        safe_reason=safe_reason(target.dependency, outcome.kind),
    )


async def probe_dependency(
    target: ProbeTarget,
    *,
    deadline: float,
    clock: ClockFn = time.monotonic,
    sleep: SleepFn = asyncio.sleep,
    wall_clock: WallClockFn = _utc_now,
    postgres_connect: PostgresConnectFn | None = None,
    tcp_connect: TcpConnectFn | None = None,
    attempt_timeout: float = ATTEMPT_TIMEOUT_SECONDS,
    retry_interval: float = RETRY_INTERVAL_SECONDS,
) -> DependencyHealthResult:
    """Probe one dependency with fresh evidence under one shared deadline.

    Each attempt opens new connections and is bounded by
    ``min(attempt_timeout, deadline - clock())``; truncation is exact. When no
    time remains the stable timeout category is reported without network
    access. Retryable categories (connect/timeout/unexpected) retry every
    ``retry_interval`` seconds until the deadline; authentication and identity
    failures are unretryable. A result completed only after the deadline is
    stale and can never turn the run into a success. Only safe categories and
    bounded static reasons are returned, never raw probe output.
    """
    if attempt_timeout <= 0:
        raise ValueError("attempt timeout must be positive")
    if retry_interval <= 0:
        raise ValueError("retry interval must be positive")
    attempt = _attempt_fn(target, postgres_connect=postgres_connect, tcp_connect=tcp_connect)
    started = clock()
    last: _AttemptOutcome | None = None
    while True:
        remaining = deadline - clock()
        if remaining <= _MIN_ATTEMPT_BUDGET_SECONDS:
            outcome = last if last is not None else _timeout_outcome(target)
            return _to_result(target, outcome, wall_clock, started, clock)
        effective = min(attempt_timeout, remaining)
        try:
            last = await asyncio.wait_for(attempt(target, effective), effective)
        except TimeoutError:
            last = _timeout_outcome(target)
        if last.kind is ProbeOutcome.READY:
            if clock() <= deadline:
                return _to_result(target, last, wall_clock, started, clock)
            # Post-deadline evidence is stale and must not flip the run.
            return _to_result(target, _timeout_outcome(target), wall_clock, started, clock)
        if last.kind in _UNRETRYABLE:
            return _to_result(target, last, wall_clock, started, clock)
        remaining = deadline - clock()
        if remaining <= _MIN_ATTEMPT_BUDGET_SECONDS:
            return _to_result(target, last, wall_clock, started, clock)
        await sleep(min(retry_interval, remaining))
