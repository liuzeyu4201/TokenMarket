"""Pure ``.env.local`` parsing and validation for the SF02 local environment.

Implements the configuration contract of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decision 6 (strict local URL grammar):

- Mode-first: ``MODE`` must be declared exactly once and exactly as ``local``
  in the file. A missing, duplicate, or non-local value fails with
  ``INVALID_MODE`` before any field, line, or URL validation runs. The file
  is the only lifecycle configuration origin; shell environment variables
  are never consulted and cannot override or supply lifecycle fields.
- The three URLs are the only host/port facts. Only the IPv4 loopback
  literal ``127.0.0.1`` is accepted (no ``localhost``, wildcard, LAN, IPv6,
  or remote address); ports are 1-65535 and pairwise distinct across the
  three URLs, so a host-port override happens only by editing its URL.
- Every decoded secret matches ``^tm_local_[A-Za-z0-9_-]{32,96}$``. Percent
  decoding happens only after full syntax validation and only for URL
  passwords; the decoded value must match the grammar, so whitespace,
  quotes, backslashes, delimiters, and control characters can never reach
  the Redis single-directive configuration or any other secret consumer.
- Empty values, ``.env.example`` placeholders, and provider-key-like values
  fail closed. Validation errors name the field only (plus recovery
  direction); supplied values, raw lines, and secrets are never echoed.
- Derived container connections replace only host/port with the canonical
  service name/container port and preserve scheme, user-info, and path.
  Displayed host endpoints carry no user-info.

The file grammar is intentionally strict: lines are ``NAME=value`` with an
uppercase name, ``#`` comment lines and blank lines are allowed, and CR/LF
inside values is rejected rather than normalized.

This module is pure: no filesystem, subprocess, network, environment, or
Docker access. Reading ``.env.local`` bytes is the caller's responsibility.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import combinations
from urllib.parse import SplitResult, unquote, urlsplit

from .models import DependencyId, LocalEnvironmentError

__all__ = [
    "DATABASE_URL_FIELD",
    "GRAFANA_ADMIN_PASSWORD_FIELD",
    "GRAFANA_ADMIN_USERNAME",
    "GRAFANA_URL_FIELD",
    "LOCAL_SECRET_PATTERN",
    "LOOPBACK_HOST",
    "MODE_FIELD",
    "REDIS_URL_FIELD",
    "DerivedConnection",
    "InvalidConfigError",
    "InvalidModeError",
    "LocalEnvironmentConfiguration",
    "parse_local_environment",
]

LOOPBACK_HOST = "127.0.0.1"
GRAFANA_ADMIN_USERNAME = "admin"

MODE_FIELD = "MODE"
DATABASE_URL_FIELD = "DATABASE_URL"
REDIS_URL_FIELD = "REDIS_URL"
GRAFANA_URL_FIELD = "GRAFANA_URL"
GRAFANA_ADMIN_PASSWORD_FIELD = "GRAFANA_ADMIN_PASSWORD"

LOCAL_SECRET_PATTERN = re.compile(r"^tm_local_[A-Za-z0-9_-]{32,96}$")

_LINE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
# Users and database names become Compose environment values and probe facts;
# a conservative identifier grammar keeps them free of percent-encoding and
# structural characters (research Decision 6 percent-encodes passwords only).
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}$")
_REDIS_DB_PATTERN = re.compile(r"^[0-9]+$")

_LIFECYCLE_FIELDS = frozenset(
    {
        MODE_FIELD,
        DATABASE_URL_FIELD,
        REDIS_URL_FIELD,
        GRAFANA_URL_FIELD,
        GRAFANA_ADMIN_PASSWORD_FIELD,
    }
)

_CONTAINER_ENDPOINTS: Mapping[DependencyId, tuple[str, int]] = {
    DependencyId.POSTGRES: ("postgres", 5432),
    DependencyId.REDIS: ("redis", 6379),
    DependencyId.GRAFANA: ("grafana", 3000),
}

_MIN_PORT = 1
_MAX_PORT = 65535

# Characters that must never appear in a raw lifecycle URL: quotes, a
# backslash, and DEL. Whitespace and C0 controls are rejected by ordinal.
_UNSAFE_URL_CHARS = frozenset(('"', "'", "\\", "\x7f"))


class InvalidModeError(LocalEnvironmentError):
    """The file mode is missing, duplicated, or not exactly ``local``."""

    code = "INVALID_MODE"


class InvalidConfigError(LocalEnvironmentError):
    """A lifecycle field is missing, malformed, a placeholder, or non-local."""

    code = "INVALID_CONFIG"

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


@dataclass(frozen=True)
class DerivedConnection:
    """Immutable in-memory projection of one validated host URL.

    ``secret`` and ``container_url`` carry credential material and are
    excluded from repr/str and equality; ``username`` is user-info and is
    excluded from repr as well. The projection is never serialized to logs,
    events, snapshots, or diagnostics; only :attr:`displayed_endpoint` is
    safe to show.
    """

    dependency_id: DependencyId
    host_scheme: str
    host_address: str
    host_port: int
    container_host: str
    container_port: int
    username: str | None = field(default=None, repr=False)
    database: str | int | None = None
    secret: str = field(default="", repr=False, compare=False)
    container_url: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        expected = _CONTAINER_ENDPOINTS.get(self.dependency_id)
        if expected is None:
            raise ValueError("unknown dependency for a derived connection")
        container_host, container_port = expected
        if self.container_host != container_host or self.container_port != container_port:
            raise ValueError("container host/port must be the canonical dependency endpoint")
        if self.host_address != LOOPBACK_HOST:
            raise ValueError("host address must be the loopback literal 127.0.0.1")
        if not _MIN_PORT <= self.host_port <= _MAX_PORT:
            raise ValueError("host port must be within 1..65535")
        if not self.container_url:
            raise ValueError("container_url is required")
        if not self.secret:
            raise ValueError("a validated local secret is required")
        if self.dependency_id is DependencyId.POSTGRES and not isinstance(self.database, str):
            raise ValueError("postgres connections require a database name")
        if self.dependency_id is DependencyId.REDIS and (
            isinstance(self.database, bool) or not isinstance(self.database, int)
        ):
            raise ValueError("redis connections require a database number")
        if self.dependency_id is DependencyId.GRAFANA and self.database is not None:
            raise ValueError("grafana connections carry no database")

    @property
    def displayed_endpoint(self) -> str:
        """Safe host endpoint with all user-info removed."""
        endpoint = f"{self.host_scheme}://{self.host_address}:{self.host_port}"
        if self.database is not None:
            endpoint = f"{endpoint}/{self.database}"
        return endpoint


@dataclass(frozen=True)
class LocalEnvironmentConfiguration:
    """Validated SF02 local configuration read only from ignored ``.env.local``.

    Holds no raw URLs; every fact lives in the three derived connections.
    ``make dev-down`` never requires, parses, or validates this entity.
    """

    mode: str
    connections: tuple[DerivedConnection, ...]

    def __post_init__(self) -> None:
        if self.mode != "local":
            raise ValueError("mode must be exactly local")
        ids = tuple(connection.dependency_id for connection in self.connections)
        expected = (DependencyId.POSTGRES, DependencyId.REDIS, DependencyId.GRAFANA)
        if ids != expected:
            raise ValueError("connections must cover postgres, redis, grafana in order")
        ports = [connection.host_port for connection in self.connections]
        if len(set(ports)) != len(ports):
            raise ValueError("host ports must be pairwise distinct")

    def connection(self, dependency_id: DependencyId) -> DerivedConnection:
        """Return the single derived connection for one required dependency."""
        for connection in self.connections:
            if connection.dependency_id is dependency_id:
                return connection
        raise KeyError(dependency_id)

    def displayed_endpoints(self) -> dict[str, str]:
        """Safe host endpoints keyed by dependency, user-info removed."""
        return {
            connection.dependency_id.value: connection.displayed_endpoint
            for connection in self.connections
        }

    def displayed_container_endpoints(self) -> dict[str, str]:
        """Safe canonical container endpoints keyed by dependency.

        Replaces only the host/port with the project-network service name and
        fixed container port; never serializes user-info or secrets (T057).
        """
        endpoints: dict[str, str] = {}
        for connection in self.connections:
            endpoint = (
                f"{connection.host_scheme}://{connection.container_host}:"
                f"{connection.container_port}"
            )
            if connection.database is not None:
                endpoint = f"{endpoint}/{connection.database}"
            endpoints[connection.dependency_id.value] = endpoint
        return endpoints


def parse_local_environment(text: str) -> LocalEnvironmentConfiguration:
    """Parse and validate ``.env.local`` content (mode-first, pure).

    The file is the only lifecycle configuration origin; shell environment
    values are never consulted. Mode validation precedes every other check,
    and every error names fields, never values.
    """
    _validate_mode(text)
    assignments = _parse_assignments(text)
    database_url = _required(assignments, DATABASE_URL_FIELD)
    redis_url = _required(assignments, REDIS_URL_FIELD)
    grafana_url = _required(assignments, GRAFANA_URL_FIELD)
    admin_password = _required(assignments, GRAFANA_ADMIN_PASSWORD_FIELD)

    pg_user, pg_secret, pg_port, pg_database = _parse_database_url(database_url)
    redis_secret, redis_port, redis_db = _parse_redis_url(redis_url)
    grafana_port = _parse_grafana_url(grafana_url)
    _validate_local_secret(GRAFANA_ADMIN_PASSWORD_FIELD, admin_password)

    _check_distinct_ports(
        (DATABASE_URL_FIELD, pg_port),
        (REDIS_URL_FIELD, redis_port),
        (GRAFANA_URL_FIELD, grafana_port),
    )

    return LocalEnvironmentConfiguration(
        mode="local",
        connections=(
            DerivedConnection(
                dependency_id=DependencyId.POSTGRES,
                host_scheme="postgresql",
                host_address=LOOPBACK_HOST,
                host_port=pg_port,
                container_host="postgres",
                container_port=5432,
                username=pg_user,
                database=pg_database,
                secret=pg_secret,
                container_url=(f"postgresql://{pg_user}:{pg_secret}@postgres:5432/{pg_database}"),
            ),
            DerivedConnection(
                dependency_id=DependencyId.REDIS,
                host_scheme="redis",
                host_address=LOOPBACK_HOST,
                host_port=redis_port,
                container_host="redis",
                container_port=6379,
                username="default",
                database=redis_db,
                secret=redis_secret,
                container_url=f"redis://default:{redis_secret}@redis:6379/{redis_db}",
            ),
            DerivedConnection(
                dependency_id=DependencyId.GRAFANA,
                host_scheme="http",
                host_address=LOOPBACK_HOST,
                host_port=grafana_port,
                container_host="grafana",
                container_port=3000,
                username=GRAFANA_ADMIN_USERNAME,
                database=None,
                secret=admin_password,
                container_url="http://grafana:3000",
            ),
        ),
    )


def _validate_mode(text: str) -> None:
    """Enforce exactly one ``MODE=local`` line before any other work."""
    values = []
    for line in text.split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith(f"{MODE_FIELD}="):
            values.append(line.partition("=")[2])
    if not values:
        raise InvalidModeError(
            "MODE must be declared exactly as 'local' in .env.local; " "add MODE=local and retry"
        )
    if len(values) > 1:
        raise InvalidModeError(
            "MODE must be declared exactly once as 'local' in .env.local; "
            "remove the duplicate MODE lines and retry"
        )
    if values[0] != "local":
        raise InvalidModeError(
            "MODE must be exactly 'local' in .env.local; local configuration "
            "cannot select or elevate to another mode"
        )


def _parse_assignments(text: str) -> dict[str, str]:
    """Strictly parse ``NAME=value`` lines; unknown fields are ignored."""
    assignments: dict[str, str] = {}
    seen_lifecycle: set[str] = set()
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        match = _LINE_PATTERN.fullmatch(line)
        if match is None:
            raise InvalidConfigError(
                f"line {number}",
                "malformed configuration line; expected NAME=value with an "
                "uppercase name and no leading whitespace",
            )
        key, value = match.group(1), match.group(2)
        if key in _LIFECYCLE_FIELDS:
            if key in seen_lifecycle:
                raise InvalidConfigError(key, "must be declared exactly once in .env.local")
            seen_lifecycle.add(key)
        assignments[key] = value
    return assignments


def _required(assignments: Mapping[str, str], field_name: str) -> str:
    value = assignments.get(field_name)
    if value is None or value == "":
        raise InvalidConfigError(
            field_name,
            "is required in .env.local; copy .env.example and set a real local value",
        )
    return value


def _reject_unsafe_url_chars(field_name: str, value: str) -> None:
    """Reject whitespace, quotes, backslashes, and control characters early."""
    for char in value:
        if ord(char) < 0x21 or char in _UNSAFE_URL_CHARS:
            raise InvalidConfigError(
                field_name,
                "must not contain whitespace, quotes, backslashes, or " "control characters",
            )


def _parse_loopback_authority(field_name: str, split: SplitResult) -> int:
    """Validate the loopback-literal host and return its explicit port."""
    if split.hostname != LOOPBACK_HOST:
        raise InvalidConfigError(field_name, "host must be the IPv4 loopback literal 127.0.0.1")
    try:
        port = split.port
    except ValueError:
        raise InvalidConfigError(field_name, "port must be a number within 1..65535") from None
    if port is None:
        raise InvalidConfigError(field_name, "must include an explicit host port")
    if not _MIN_PORT <= port <= _MAX_PORT:
        raise InvalidConfigError(field_name, "port must be within 1..65535")
    return port


def _decode_password(field_name: str, raw_password: str | None) -> str:
    """Percent-decode a URL password, then enforce the synthetic grammar."""
    if not raw_password:
        raise InvalidConfigError(field_name, "password is required")
    try:
        decoded = unquote(raw_password, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InvalidConfigError(
            field_name, "password percent-encoding is not valid UTF-8"
        ) from None
    return _validate_local_secret(field_name, decoded)


def _validate_local_secret(field_name: str, value: str) -> str:
    if not LOCAL_SECRET_PATTERN.fullmatch(value):
        raise InvalidConfigError(
            field_name,
            "secret must match the synthetic local grammar tm_local_ followed "
            "by 32-96 URL-safe characters; generate one per .env.example "
            "guidance",
        )
    return value


def _single_path_segment(field_name: str, path: str, what: str) -> str:
    if not path.startswith("/"):
        raise InvalidConfigError(field_name, f"must include a {what}")
    segment = path[1:]
    if not segment or "/" in segment:
        raise InvalidConfigError(field_name, f"must include exactly one {what} path segment")
    return segment


def _parse_database_url(value: str) -> tuple[str, str, int, str]:
    field_name = DATABASE_URL_FIELD
    _reject_unsafe_url_chars(field_name, value)
    if not value.startswith("postgresql://"):
        raise InvalidConfigError(field_name, "must use the postgresql:// scheme")
    split = urlsplit(value)
    port = _parse_loopback_authority(field_name, split)
    username = split.username
    if not username or not _IDENTIFIER_PATTERN.fullmatch(username):
        raise InvalidConfigError(field_name, "user must be a non-empty local identifier")
    secret = _decode_password(field_name, split.password)
    if split.query or split.fragment:
        raise InvalidConfigError(field_name, "must not contain a query string or fragment")
    database = _single_path_segment(field_name, split.path, "database name")
    if not _IDENTIFIER_PATTERN.fullmatch(database):
        raise InvalidConfigError(field_name, "database must be a non-empty local identifier")
    return username, secret, port, database


def _parse_redis_url(value: str) -> tuple[str, int, int]:
    field_name = REDIS_URL_FIELD
    _reject_unsafe_url_chars(field_name, value)
    if not value.startswith("redis://"):
        raise InvalidConfigError(field_name, "must use the redis:// scheme")
    split = urlsplit(value)
    port = _parse_loopback_authority(field_name, split)
    if split.username != "default":
        raise InvalidConfigError(field_name, "user must be the fixed name 'default'")
    secret = _decode_password(field_name, split.password)
    if split.query or split.fragment:
        raise InvalidConfigError(field_name, "must not contain a query string or fragment")
    segment = _single_path_segment(field_name, split.path, "database number")
    if not _REDIS_DB_PATTERN.fullmatch(segment):
        raise InvalidConfigError(field_name, "database must be a non-negative integer")
    return secret, port, int(segment)


def _parse_grafana_url(value: str) -> int:
    field_name = GRAFANA_URL_FIELD
    _reject_unsafe_url_chars(field_name, value)
    if not value.startswith("http://"):
        raise InvalidConfigError(field_name, "must use the http:// scheme")
    split = urlsplit(value)
    if split.username is not None or split.password is not None:
        raise InvalidConfigError(
            field_name,
            "must not contain user-info; the administrator password is the "
            "separate GRAFANA_ADMIN_PASSWORD field",
        )
    port = _parse_loopback_authority(field_name, split)
    if split.path not in ("", "/"):
        raise InvalidConfigError(field_name, "path must be empty or the root '/' only")
    if split.query or split.fragment:
        raise InvalidConfigError(field_name, "must not contain a query string or fragment")
    return port


def _check_distinct_ports(*field_ports: tuple[str, int]) -> None:
    """Enforce pairwise-distinct host ports across the three URL fields."""
    for (field_a, port_a), (field_b, port_b) in combinations(field_ports, 2):
        if port_a == port_b:
            raise InvalidConfigError(
                f"{field_a} and {field_b}",
                "host ports must be pairwise distinct; change one URL port",
            )
