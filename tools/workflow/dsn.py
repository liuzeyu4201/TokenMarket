"""PostgreSQL DSN parsing for fail-closed host attestation.

Validates the *effective* connection target using URI and keyword/value
grammar. Query-parameter host overrides, sockets, multi-host lists, and
ambiguous forms are rejected rather than forwarded to a driver.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlparse

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}

# Driver parameters that can retarget the connected server or inject credentials.
_HOST_AFFECTING_KEYS = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "passfile",
        "service",
        "options",
        "requiressl",
        "sslrootcert",
        "sslkey",
        "sslcert",
        "sslpassword",
        "sslcrl",
        "keepalives",
        "unix_socket",
        "unix_socket_dir",
        "unix_socket_directories",
    }
)

_CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "password",
        "passfile",
        "token",
        "secret",
        "pwd",
        "sslpassword",
    }
)

_URI_SCHEMES = frozenset(
    {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
        "postgresql+asyncpg",
    }
)

_KV_PRIMARY_KEYS = frozenset({"host", "port", "user", "password", "dbname", "database"})

_KW_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")


class DSNError(ValueError):
    """Raised when a DSN is malformed or retargets the host."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedDSN:
    scheme: str
    username: str
    password: str
    host: str
    port: int | None
    database: str
    query: tuple[tuple[str, str], ...]
    form: str  # "uri" | "keyword"

    def hostname(self) -> str:
        return (self.host or "").strip().lower().strip("[]")


def _is_loopback_host(host: str) -> bool:
    text = (host or "").strip().lower().strip("[]")
    if not text:
        return False
    if text in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _reject_socket_or_multi(host: str) -> None:
    text = (host or "").strip()
    if not text:
        raise DSNError("INVALID_TARGET", "database URL is missing a host")
    if "/" in text or text.startswith("@"):
        raise DSNError("INVALID_TARGET", "unix-socket database URLs are not allowed")
    if "," in text:
        raise DSNError("INVALID_TARGET", "multi-host database URLs are not allowed")


def _parse_keyword_value(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    matches = list(_KW_RE.finditer(text))
    if not matches:
        raise DSNError("INVALID_TARGET", "database URL is malformed")
    for i, match in enumerate(matches):
        key = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[key] = text[start:end].strip().strip("'\"")
    return out


def parse_postgres_dsn(url: str) -> ParsedDSN:
    """Parse a PostgreSQL URI or keyword/value DSN; fail closed on ambiguity."""
    text = (url or "").strip()
    if not text:
        raise DSNError("INVALID_TARGET", "database URL is missing")

    if "://" in text:
        parsed = urlparse(text)
        scheme = (parsed.scheme or "").lower()
        if scheme not in _URI_SCHEMES:
            raise DSNError("INVALID_TARGET", f"unsupported database URL scheme {scheme!r}")
        host = unquote(parsed.hostname or "") if parsed.hostname else ""
        # urlparse splits on commas poorly; detect multi-host in netloc.
        netloc = parsed.netloc or ""
        if "," in netloc:
            raise DSNError("INVALID_TARGET", "multi-host database URLs are not allowed")
        _reject_socket_or_multi(host)
        query = tuple(parse_qsl(parsed.query, keep_blank_values=True))
        database = unquote((parsed.path or "").lstrip("/"))
        username = unquote(parsed.username or "") if parsed.username else ""
        password = unquote(parsed.password or "") if parsed.password else ""
        return ParsedDSN(
            scheme=scheme,
            username=username,
            password=password,
            host=host,
            port=parsed.port,
            database=database,
            query=query,
            form="uri",
        )

    # libpq keyword/value
    kv = _parse_keyword_value(text)
    lowered = {k.lower(): v for k, v in kv.items()}
    host = lowered.get("hostaddr") or lowered.get("host") or ""
    _reject_socket_or_multi(host)
    port_raw = lowered.get("port") or ""
    port = int(port_raw) if port_raw.isdigit() else None
    return ParsedDSN(
        scheme="postgresql",
        username=lowered.get("user") or "",
        password=lowered.get("password") or "",
        host=host,
        port=port,
        database=lowered.get("dbname") or lowered.get("database") or "",
        query=tuple((k, v) for k, v in kv.items()),
        form="keyword",
    )


def assert_no_host_override(url: str) -> ParsedDSN:
    """Reject DSNs whose query/keyword form can retarget host or inject a passfile."""
    parsed = parse_postgres_dsn(url)
    keys = {k.lower(): v for k, v in parsed.query}
    if parsed.form == "uri":
        for key, _value in parsed.query:
            if key.lower() in _HOST_AFFECTING_KEYS:
                raise DSNError(
                    "INVALID_TARGET",
                    f"database URL query parameter {key!r} can retarget the host",
                )
    else:
        if "passfile" in keys:
            raise DSNError(
                "INVALID_TARGET",
                "database URL query parameter 'passfile' can retarget the host",
            )
        if "host" in keys and "hostaddr" in keys:
            raise DSNError(
                "INVALID_TARGET",
                "database URL query parameter 'hostaddr' can retarget the host",
            )
        for key in keys:
            if key in _HOST_AFFECTING_KEYS and key not in _KV_PRIMARY_KEYS | {"hostaddr"}:
                raise DSNError(
                    "INVALID_TARGET",
                    f"database URL query parameter {key!r} can retarget the host",
                )
    _reject_socket_or_multi(parsed.host)
    return parsed


def dsn_is_production_shaped(url: str) -> bool:
    """True when the effective host is not loopback, or the DSN is ambiguous."""
    text = (url or "").strip()
    if not text:
        return False
    try:
        parsed = assert_no_host_override(text)
    except DSNError:
        return True
    host = parsed.hostname()
    if not host:
        return True
    return not _is_loopback_host(host)


def attested_test_dsn(url: str) -> str:
    """Return a canonical loopback URI with host-affecting query parameters removed.

    Rejects production-shaped hosts, sockets, multi-host forms, and host-retargeting
    query keys. Safe parameters such as sslmode are not forwarded so both migration
    owners receive an identical isolated DSN.
    """
    parsed = assert_no_host_override(url)
    if not _is_loopback_host(parsed.hostname()):
        raise DSNError(
            "INVALID_TARGET",
            "mode=test refuses a production-shaped database URL before Alembic",
        )
    user = parsed.username
    password = parsed.password
    host = parsed.hostname()
    if host == "::1" or host == "0:0:0:0:0:0:0:1":
        host = "[::1]"
    auth = ""
    if user:
        auth = user
        if password:
            auth += f":{password}"
        auth += "@"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.database
    path = f"/{database}" if database else ""
    return f"postgresql://{auth}{host}{port}{path}"


def credential_query_keys(url: str) -> list[str]:
    """Return credential-bearing query keys present in *url* (any case)."""
    text = (url or "").strip()
    if not text:
        return []
    try:
        parsed = parse_postgres_dsn(text)
    except DSNError:
        # Best-effort scan of the raw query string.
        if "?" not in text:
            return []
        _, _, query = text.partition("?")
        parsed_query = parse_qsl(query, keep_blank_values=True)
        return [k for k, _ in parsed_query if k.lower() in _CREDENTIAL_QUERY_KEYS]
    return [k for k, _ in parsed.query if k.lower() in _CREDENTIAL_QUERY_KEYS]


def redact_dsn(url: str) -> str:
    """Structurally redact userinfo and credential-bearing query fields."""
    text = (url or "").strip()
    if not text:
        return ""
    try:
        if "://" in text:
            parsed = urlparse(text)
            host = parsed.hostname or ""
            netloc = host
            if parsed.port:
                netloc = f"{host}:{parsed.port}"
            if parsed.username is not None:
                netloc = f"{parsed.username}:[REDACTED]@{netloc}"
            query_pairs = []
            for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                if key.lower() in _CREDENTIAL_QUERY_KEYS:
                    query_pairs.append((key, "[REDACTED]"))
                else:
                    query_pairs.append((key, value))
            from urllib.parse import urlencode, urlunparse

            query = urlencode(query_pairs)
            return urlunparse(
                (
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    query,
                    parsed.fragment,
                )
            )
        kv = _parse_keyword_value(text)
        parts = []
        for key, value in kv.items():
            if key.lower() in _CREDENTIAL_QUERY_KEYS or key.lower() == "password":
                parts.append(f"{key}=[REDACTED]")
            else:
                parts.append(f"{key}={value}")
        return " ".join(parts)
    except Exception:
        # Last-resort: never return the original secret-bearing string.
        return "postgresql://[REDACTED]"
