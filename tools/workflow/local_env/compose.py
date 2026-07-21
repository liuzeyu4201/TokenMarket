"""Local runtime preflight and Docker Compose adapter (SF02 T028/T030).

Implements the Compose invocation contract of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 2, 3, 4, 7, 9 and 12:

- Every Compose command uses a fixed argument order with the explicit project
  ID and the secure ``0700`` runtime project directory derived only from
  ``project_id``; the workspace path never appears in arguments or labels.
- ``infra/docker/compose.local.yml`` is verified as a regular non-symlink file
  whose bytes equal the committed Git blob *before any Compose access*; the
  verified bytes are transported over stdin with ``-f -``. A dirty, replaced,
  symlinked, or uncommitted asset fails closed.
- Runtime preflight is read-only and happens before any state change: supported
  host platform (macOS arm64, Linux x86_64), local Unix endpoint only (remote
  ``DOCKER_HOST``/contexts rejected), maintained Docker 29.5.3 / Compose 5.1.4
  versions, Linux daemon on the native architecture, and required Compose
  options/JSON capabilities.
- Images are inspected locally first; only missing pinned digests are pulled
  (pull is reported per dependency, separately from readiness), then every
  image is verified against the reviewed index/current-platform child digest
  and native platform. Reconcile uses ``up --detach --pull never`` so the
  readiness phase never touches the registry.
- Captured ``ps --format json`` state is parsed tolerantly (unknown fields
  allowed, malformed/partial input rejected); ownership is authorized by the
  exact project plus the full 64-hex fingerprint; publishers must be
  loopback-only; port preflight is bind-only and never sends protocol data.
- Every subprocess runs with a timeout; on timeout the process group is
  terminated within the bound and the failure maps to a stable redacted
  diagnostic. stderr/stdout/argv/env never leak into errors.
- Secret material exists only in a dedicated child-process environment mapping
  built per invocation (T030): the PostgreSQL/Grafana password file contents,
  an injection-safe single-directive ``requirepass`` Redis config, plus
  parse-only teardown placeholders. Non-secret derived variables (user,
  database, host ports) join the same child mapping through ``derived_env``
  and can never override the adapter-owned secret/label variables. Mappings
  are never merged into the parent environment, printed, returned in
  exceptions, or retained after the call.

Docker 29 with the containerd image store records the pulled OCI *index*
digest in ``RepoDigests``; the legacy graph driver recorded the platform
*child* digest. Local verification therefore accepts either the reviewed index
or the current-platform child digest and additionally requires the native
``Os``/``Architecture``; anything else fails closed as ``IMAGE_UNAVAILABLE``.
"""

from __future__ import annotations

import json
import os
import platform
import re
import signal
import socket
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .identity import COMPOSE_PROJECT_DIR_NAME, WorkspaceIdentity
from .models import (
    ComposeSecretMaterial,
    DependencyId,
    LocalDependencyDefinition,
    LocalDependencyManifest,
    LocalEnvironmentError,
    OwnershipConflictError,
    SecretCleanupState,
    SecretPurpose,
)

# ---------------------------------------------------------------------------
# Error taxonomy (stable diagnostic codes, always redacted messages)


class ToolMissingError(LocalEnvironmentError):
    """The Docker CLI or Compose plugin is absent."""

    code = "TOOL_MISSING"


class UnsupportedRuntimeError(LocalEnvironmentError):
    """Host platform, endpoint, version, daemon, or capability is unsupported."""

    code = "TOOL_VERSION_UNSUPPORTED"


class ImageUnavailableError(LocalEnvironmentError):
    """A pinned image is missing, unpullable, or fails identity verification."""

    code = "IMAGE_UNAVAILABLE"


class PortConflictError(LocalEnvironmentError):
    """A desired loopback port is owned elsewhere or lost to a bind race."""

    code = "PORT_CONFLICT"


class ComposeAssetError(LocalEnvironmentError):
    """The Compose asset is missing, replaced, dirty, or not a regular file."""

    code = "CONTRACT_DRIFT"


class ComposeCommandError(LocalEnvironmentError):
    """A bounded Compose invocation failed; state is retained for inspection."""

    code = "STEP_FAILED"


class ComposeStateParseError(LocalEnvironmentError):
    """Captured Compose JSON state is malformed or misses required fields."""

    code = "STEP_FAILED"


class InvalidSecretMaterialError(LocalEnvironmentError):
    """Secret material violates the local synthetic-secret grammar."""

    code = "INVALID_CONFIG"


# ---------------------------------------------------------------------------
# Constants


COMPOSE_FILE_RELATIVE_PATH = "infra/docker/compose.local.yml"

LABEL_REPOSITORY = "com.tokenmarket.repository"
LABEL_WORKSPACE_ID = "com.tokenmarket.workspace-id"
LABEL_WORKSPACE_FINGERPRINT = "com.tokenmarket.workspace-fingerprint"

# Dedicated child-only environment variables consumed by the Compose model's
# environment-source secrets and workspace labels. These names are part of the
# adapter contract with infra/docker/compose.local.yml (T027).
POSTGRES_PASSWORD_ENV = "TOKENMARKET_POSTGRES_PASSWORD"
REDIS_CONFIG_ENV = "TOKENMARKET_REDIS_CONFIG"
GRAFANA_ADMIN_PASSWORD_ENV = "TOKENMARKET_GRAFANA_ADMIN_PASSWORD"
WORKSPACE_ID_ENV = "TOKENMARKET_WORKSPACE_ID"
WORKSPACE_FINGERPRINT_ENV = "TOKENMARKET_WORKSPACE_FINGERPRINT"

# Non-secret derived child variables the Compose model interpolates. Values
# come from the validated local configuration (wired by the lifecycle
# orchestrator) and are never user configuration overrides.
POSTGRES_USER_ENV = "TOKENMARKET_POSTGRES_USER"
POSTGRES_DB_ENV = "TOKENMARKET_POSTGRES_DB"
POSTGRES_HOST_PORT_ENV = "TOKENMARKET_POSTGRES_HOST_PORT"
REDIS_HOST_PORT_ENV = "TOKENMARKET_REDIS_HOST_PORT"
GRAFANA_HOST_PORT_ENV = "TOKENMARKET_GRAFANA_HOST_PORT"

# Adapter-owned child variables that derived values may never override.
_RESERVED_CHILD_ENV = frozenset(
    {
        POSTGRES_PASSWORD_ENV,
        REDIS_CONFIG_ENV,
        GRAFANA_ADMIN_PASSWORD_ENV,
        WORKSPACE_ID_ENV,
        WORKSPACE_FINGERPRINT_ENV,
    }
)

# The strict local synthetic-secret grammar from the configuration contract.
# It excludes whitespace, quotes, backslashes, delimiters, and control
# characters, so a generated Redis config cannot gain a second directive.
LOCAL_SECRET_GRAMMAR = re.compile(r"^tm_local_[A-Za-z0-9_-]{32,96}$")

# Fixed parse-only placeholder for config-free teardown: it matches the
# grammar so Compose can parse the model, but it is never a working credential.
TEARDOWN_PLACEHOLDER_SECRET = "tm_local_" + "0" * 32

PREFLIGHT_COMMAND_TIMEOUT_SECONDS = 15.0
STATE_COMMAND_TIMEOUT_SECONDS = 15.0
IMAGE_INSPECT_TIMEOUT_SECONDS = 15.0
DEFAULT_PULL_TIMEOUT_SECONDS = 600.0

_LOOPBACK_BIND_ADDRESS = "127.0.0.1"
_CONTAINER_PLATFORM = {"darwin/arm64": "linux/arm64", "linux/amd64": "linux/amd64"}
_DAEMON_ARCH = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}
_DOCKER_VERSION_RE = re.compile(r"Docker version (\d+\.\d+\.\d+)")
_COMPOSE_VERSION_RE = re.compile(r"Compose version v?(\d+\.\d+\.\d+)")
_PORT_RACE_MARKERS = (
    "address already in use",
    "port is already allocated",
    "ports are not available",
    "bind for",
    "failed to bind",
)

RunFn = Callable[..., subprocess.CompletedProcess[str]]
GitShowFn = Callable[[str], bytes]
BindCheckFn = Callable[[str, int], None]


# ---------------------------------------------------------------------------
# Injectable default seams


def default_run(args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Bounded ``subprocess.run`` replacement: kill the process group on timeout.

    The child runs in its own session so a timeout can terminate the whole
    process group within the bound instead of orphaning Compose children.
    """
    argv = [str(arg) for arg in args]
    timeout = kwargs.get("timeout")
    env = kwargs.get("env")
    input_text = kwargs.get("input")
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def default_git_show(repo_root: Path) -> GitShowFn:
    """Read-only ``git show HEAD:<path>`` blob reader scoped to the repository."""

    def _show(relative_path: str) -> bytes:
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative_path}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ComposeAssetError(
                "compose asset is not readable from the committed Git blob; "
                "failing closed before Compose access"
            )
        return result.stdout

    return _show


def default_bind_check(host: str, port: int) -> None:
    """Bind-only loopback availability probe; never sends protocol data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        raise PortConflictError(
            f"loopback port {port} is unavailable; free the port or change its URL"
        ) from None
    finally:
        probe.close()


def detect_host_platform(system: str | None = None, machine: str | None = None) -> str:
    """Return the supported host platform ID or fail closed."""
    normalized_system = platform.system().lower() if system is None else system.lower()
    normalized_machine = platform.machine().lower() if machine is None else machine.lower()
    if normalized_system == "darwin" and normalized_machine in ("arm64", "aarch64"):
        return "darwin/arm64"
    if normalized_system == "linux" and normalized_machine in ("x86_64", "amd64"):
        return "linux/amd64"
    raise UnsupportedRuntimeError(
        f"unsupported host platform {normalized_system}/{normalized_machine}; "
        "SF02 supports macOS arm64 and Linux x86_64 only"
    )


# ---------------------------------------------------------------------------
# Captured runtime facts and state entities


@dataclass(frozen=True)
class RuntimeFacts:
    """Read-only preflight evidence about the local Docker runtime."""

    host_platform: str
    container_platform: str
    docker_version: str
    compose_version: str
    daemon_arch: str


@dataclass(frozen=True)
class PublisherInfo:
    """One published port from captured Compose JSON state."""

    host_ip: str
    target_port: int
    published_port: int
    protocol: str


@dataclass(frozen=True)
class ServiceState:
    """One captured per-service Compose state record (raw adapter view)."""

    project: str
    service: str
    state: str
    health: str
    labels: Mapping[str, str]
    publishers: tuple[PublisherInfo, ...]


@dataclass(frozen=True)
class ImagePullRecord:
    """Per-dependency pull evidence, reported separately from readiness."""

    dependency: DependencyId
    pulled: bool


def _require_str(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ComposeStateParseError(f"compose state record is missing required field {key!r}")
    return value


def _parse_labels(raw: Any) -> dict[str, str]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, str):
        raise ComposeStateParseError("compose state labels must be a string")
    labels: dict[str, str] = {}
    for entry in raw.split(","):
        if not entry:
            continue
        key, separator, value = entry.partition("=")
        if not separator or not key:
            raise ComposeStateParseError("compose state labels are malformed")
        labels[key] = value
    return labels


def _parse_publishers(raw: Any) -> tuple[PublisherInfo, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ComposeStateParseError("compose state publishers must be a list")
    publishers: list[PublisherInfo] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ComposeStateParseError("compose state publisher entries must be objects")
        host = entry.get("URL")
        target = entry.get("TargetPort")
        published = entry.get("PublishedPort")
        protocol = entry.get("Protocol")
        if not isinstance(host, str) or not isinstance(protocol, str):
            raise ComposeStateParseError("compose state publisher fields are malformed")
        if isinstance(target, bool) or not isinstance(target, int):
            raise ComposeStateParseError("compose state publisher fields are malformed")
        if isinstance(published, bool) or not isinstance(published, int):
            raise ComposeStateParseError("compose state publisher fields are malformed")
        publishers.append(
            PublisherInfo(
                host_ip=host,
                target_port=target,
                published_port=published,
                protocol=protocol,
            )
        )
    return tuple(publishers)


def _parse_record(value: Any) -> ServiceState:
    if not isinstance(value, Mapping):
        raise ComposeStateParseError("compose state entries must be JSON objects")
    health = value.get("Health", "")
    if not isinstance(health, str):
        raise ComposeStateParseError("compose state health must be a string")
    return ServiceState(
        project=_require_str(value, "Project"),
        service=_require_str(value, "Service"),
        state=_require_str(value, "State"),
        health=health,
        labels=_parse_labels(value.get("Labels", "")),
        publishers=_parse_publishers(value.get("Publishers")),
    )


def parse_ps_json(text: str) -> tuple[ServiceState, ...]:
    """Parse ``ps --format json`` output (JSONL or array) into service records.

    Unknown fields are tolerated; malformed or partial input fails closed.
    Raw output is never echoed into errors.
    """
    stripped = text.strip()
    if not stripped:
        return ()
    items: list[Any]
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        items = []
        for line in stripped.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            try:
                items.append(json.loads(candidate))
            except json.JSONDecodeError:
                raise ComposeStateParseError("compose state output is not valid JSON") from None
    else:
        if isinstance(parsed, list):
            items = list(parsed)
        elif isinstance(parsed, Mapping):
            items = [parsed]
        else:
            raise ComposeStateParseError(
                "compose state output must be JSON objects or a list"
            ) from None
    return tuple(_parse_record(item) for item in items)


# ---------------------------------------------------------------------------
# T030: dedicated child-only secret material


@dataclass(frozen=True)
class ComposeSecretSet:
    """The three dedicated child-only secret mappings for one invocation.

    The mapping exists only to be passed to a single Compose child process;
    it is never merged into the parent environment, printed, returned in
    exceptions, or retained after the call. Secret bytes stay excluded from
    repr/equality through :class:`ComposeSecretMaterial`.
    """

    postgres_password: ComposeSecretMaterial
    redis_config: ComposeSecretMaterial
    grafana_admin_password: ComposeSecretMaterial

    def _materials(self) -> tuple[ComposeSecretMaterial, ...]:
        return (
            self.postgres_password,
            self.redis_config,
            self.grafana_admin_password,
        )

    def child_mapping(self) -> dict[str, str]:
        """Return the fresh child-environment mapping; fails once released."""
        for material in self._materials():
            if material.cleanup_state is not SecretCleanupState.IN_MEMORY:
                raise InvalidSecretMaterialError(
                    "secret material has been released; build fresh material "
                    "for a new Compose invocation"
                )
        return {
            POSTGRES_PASSWORD_ENV: self.postgres_password.secret,
            REDIS_CONFIG_ENV: self.redis_config.secret,
            GRAFANA_ADMIN_PASSWORD_ENV: self.grafana_admin_password.secret,
        }

    def release(self) -> ComposeSecretSet:
        """Drop every secret byte after the Compose child process has ended."""
        return ComposeSecretSet(
            postgres_password=self.postgres_password.release(),
            redis_config=self.redis_config.release(),
            grafana_admin_password=self.grafana_admin_password.release(),
        )


def _require_local_secret(value: str, source_field: str) -> str:
    if not LOCAL_SECRET_GRAMMAR.fullmatch(value):
        raise InvalidSecretMaterialError(
            f"{source_field} does not match the local synthetic-secret grammar; "
            "refusing to build Compose secret material"
        )
    return value


def build_redis_config(redis_password: str) -> str:
    """Render the injection-safe single-directive ``redis.conf`` secret content."""
    password = _require_local_secret(redis_password, "REDIS_URL")
    return f"requirepass {password}\n"


def _material(
    identity: WorkspaceIdentity,
    definition: LocalDependencyDefinition,
    *,
    purpose: SecretPurpose,
    source_field: str,
    secret: str,
) -> ComposeSecretMaterial:
    return ComposeSecretMaterial(
        project_id=identity.project_id,
        purpose=purpose,
        source_field=source_field,
        container_owner_uid=definition.runtime_uid,
        container_owner_gid=definition.runtime_gid,
        secret=secret,
    )


def build_secret_material(
    manifest: LocalDependencyManifest,
    identity: WorkspaceIdentity,
    *,
    postgres_password: str,
    redis_password: str,
    grafana_admin_password: str,
) -> ComposeSecretSet:
    """Build the dedicated child-only mappings from validated local secrets.

    The strict grammar is re-validated here as defense in depth so the Redis
    config can never gain a second directive; errors name the field only.
    Ownership/mode metadata comes from the reviewed manifest runtime UID/GID.
    """
    postgres = manifest.dependency(DependencyId.POSTGRES)
    redis_dep = manifest.dependency(DependencyId.REDIS)
    grafana = manifest.dependency(DependencyId.GRAFANA)
    return ComposeSecretSet(
        postgres_password=_material(
            identity,
            postgres,
            purpose=SecretPurpose.POSTGRES_PASSWORD,
            source_field="DATABASE_URL",
            secret=_require_local_secret(postgres_password, "DATABASE_URL"),
        ),
        redis_config=_material(
            identity,
            redis_dep,
            purpose=SecretPurpose.REDIS_CONFIG,
            source_field="REDIS_URL",
            secret=build_redis_config(redis_password),
        ),
        grafana_admin_password=_material(
            identity,
            grafana,
            purpose=SecretPurpose.GRAFANA_ADMIN_PASSWORD,
            source_field="GRAFANA_ADMIN_PASSWORD",
            secret=_require_local_secret(grafana_admin_password, "GRAFANA_ADMIN_PASSWORD"),
        ),
    )


def build_teardown_placeholders(
    manifest: LocalDependencyManifest,
    identity: WorkspaceIdentity,
) -> ComposeSecretSet:
    """Build parse-only mappings for the config-free teardown path (down).

    Values satisfy the synthetic-secret grammar so Compose can parse the
    verified model, but they are fixed non-credentials with no real meaning.
    The down command itself is a later task (T043); this is the parse surface.
    """
    postgres = manifest.dependency(DependencyId.POSTGRES)
    redis_dep = manifest.dependency(DependencyId.REDIS)
    grafana = manifest.dependency(DependencyId.GRAFANA)
    return ComposeSecretSet(
        postgres_password=_material(
            identity,
            postgres,
            purpose=SecretPurpose.TEARDOWN_PLACEHOLDER,
            source_field="DATABASE_URL",
            secret=TEARDOWN_PLACEHOLDER_SECRET,
        ),
        redis_config=_material(
            identity,
            redis_dep,
            purpose=SecretPurpose.TEARDOWN_PLACEHOLDER,
            source_field="REDIS_URL",
            secret=f"requirepass {TEARDOWN_PLACEHOLDER_SECRET}\n",
        ),
        grafana_admin_password=_material(
            identity,
            grafana,
            purpose=SecretPurpose.TEARDOWN_PLACEHOLDER,
            source_field="GRAFANA_ADMIN_PASSWORD",
            secret=TEARDOWN_PLACEHOLDER_SECRET,
        ),
    )


# ---------------------------------------------------------------------------
# The adapter


def _indicates_port_race(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _PORT_RACE_MARKERS)


class ComposeAdapter:
    """Verified-stdin, safe-project-dir Docker Compose adapter.

    All side effects flow through injected seams (subprocess runner, git blob
    reader, bind checker, environment, host platform) so unit tests never
    touch a real daemon; the defaults provide the real bounded behavior.
    """

    def __init__(
        self,
        *,
        manifest: LocalDependencyManifest,
        identity: WorkspaceIdentity,
        project_dir: Path,
        repo_root: Path,
        run: RunFn | None = None,
        git_show: GitShowFn | None = None,
        environ: Mapping[str, str] | None = None,
        host_platform: str | None = None,
        bind_check: BindCheckFn | None = None,
        pull_timeout_seconds: float = DEFAULT_PULL_TIMEOUT_SECONDS,
    ) -> None:
        if pull_timeout_seconds <= 0:
            raise ValueError("pull_timeout_seconds must be positive")
        self._manifest = manifest
        self._identity = identity
        self._compose_project_dir = project_dir / COMPOSE_PROJECT_DIR_NAME
        self._repo_root = repo_root
        self._run: RunFn = default_run if run is None else run
        self._git_show = default_git_show(repo_root) if git_show is None else git_show
        self._environ = dict(os.environ) if environ is None else dict(environ)
        self._host_platform = host_platform
        self._bind_check = default_bind_check if bind_check is None else bind_check
        self._pull_timeout_seconds = pull_timeout_seconds

    # -- subprocess plumbing -------------------------------------------------

    def _spawn(
        self,
        argv: list[str],
        *,
        timeout_seconds: float,
        input_text: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_error: LocalEnvironmentError,
    ) -> subprocess.CompletedProcess[str]:
        """Run one bounded subprocess; never leak raw output into errors."""
        try:
            return self._run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                input=input_text,
                env=dict(env) if env is not None else None,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise ToolMissingError(
                "the docker CLI is not installed or not on PATH; install the "
                "reviewed toolchain externally"
            ) from exc
        except subprocess.TimeoutExpired:
            raise timeout_error from None

    def _compose_argv(self, *args: str, with_stdin_file: bool = False) -> list[str]:
        """Build the fixed-order Compose argument vector (no workspace path)."""
        argv = [
            "docker",
            "compose",
            "--project-name",
            self._identity.project_id,
            "--project-directory",
            str(self._compose_project_dir),
        ]
        if with_stdin_file:
            argv += ["-f", "-"]
        argv += ["--ansi", "never", *args]
        return argv

    # -- committed-blob verification -----------------------------------------

    def verified_compose_bytes(self) -> bytes:
        """Return the on-disk asset bytes only if they equal the committed blob.

        Fails closed on a missing, symlinked, non-regular, dirty, or replaced
        asset *before any Compose access*.
        """
        path = self._repo_root / COMPOSE_FILE_RELATIVE_PATH
        try:
            file_stat = os.lstat(path)
        except OSError as exc:
            raise ComposeAssetError(
                "compose asset is missing; failing closed before Compose access"
            ) from exc
        if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
            raise ComposeAssetError(
                "compose asset must be a regular non-symlink file; failing closed"
            )
        try:
            on_disk = path.read_bytes()
        except OSError as exc:
            raise ComposeAssetError(
                "compose asset is unreadable; failing closed before Compose access"
            ) from exc
        try:
            committed = self._git_show(COMPOSE_FILE_RELATIVE_PATH)
        except LocalEnvironmentError:
            raise
        except Exception as exc:
            raise ComposeAssetError(
                "compose asset committed bytes are unreadable; failing closed"
            ) from exc
        if on_disk != committed:
            raise ComposeAssetError(
                "compose asset differs from the committed Git blob; failing "
                "closed before Compose access"
            )
        return on_disk

    # -- read-only runtime preflight ------------------------------------------

    def verify_runtime(self) -> RuntimeFacts:
        """Run the read-only local runtime preflight in the contracted order."""
        host = self._host_platform or detect_host_platform()
        if host not in self._manifest.runtime.hosts:
            raise UnsupportedRuntimeError(
                f"unsupported host platform {host!r}; SF02 supports macOS arm64 "
                "and Linux x86_64 only"
            )
        self._require_local_docker_host()
        docker_version = self._verified_docker_version()
        compose_version = self._verified_compose_version()
        self._require_local_endpoint()
        daemon_arch = self._daemon_architecture(host)
        self._require_compose_capabilities()
        return RuntimeFacts(
            host_platform=host,
            container_platform=_CONTAINER_PLATFORM[host],
            docker_version=docker_version,
            compose_version=compose_version,
            daemon_arch=daemon_arch,
        )

    def _require_local_docker_host(self) -> None:
        docker_host = self._environ.get("DOCKER_HOST", "").strip()
        if not docker_host:
            return
        if not docker_host.startswith("unix://"):
            raise UnsupportedRuntimeError(
                "remote Docker endpoints are not supported; DOCKER_HOST must "
                "be a local Unix socket"
            )

    def _verified_docker_version(self) -> str:
        result = self._spawn(
            ["docker", "--version"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "docker version check exceeded its bounded execution time"
            ),
        )
        if result.returncode != 0:
            raise ToolMissingError(
                "the docker CLI is unavailable; install the reviewed toolchain externally"
            )
        match = _DOCKER_VERSION_RE.search(result.stdout)
        if match is None:
            raise UnsupportedRuntimeError("docker CLI version could not be determined")
        version = match.group(1)
        if version != self._manifest.runtime.docker_version:
            raise UnsupportedRuntimeError(
                f"docker CLI version {version} does not match the maintained "
                f"{self._manifest.runtime.docker_version}"
            )
        return version

    def _verified_compose_version(self) -> str:
        result = self._spawn(
            ["docker", "compose", "version"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "compose version check exceeded its bounded execution time"
            ),
        )
        if result.returncode != 0:
            raise ToolMissingError(
                "the Docker Compose plugin is unavailable; install the reviewed "
                "toolchain externally"
            )
        match = _COMPOSE_VERSION_RE.search(result.stdout)
        if match is None:
            raise UnsupportedRuntimeError("compose version could not be determined")
        version = match.group(1)
        if version != self._manifest.runtime.compose_version:
            raise UnsupportedRuntimeError(
                f"compose version {version} does not match the maintained "
                f"{self._manifest.runtime.compose_version}"
            )
        return version

    def _require_local_endpoint(self) -> None:
        result = self._spawn(
            ["docker", "context", "inspect", "--format", "json"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "docker endpoint check exceeded its bounded execution time"
            ),
        )
        if result.returncode != 0:
            raise UnsupportedRuntimeError("the active docker context is unavailable")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise UnsupportedRuntimeError("the active docker context could not be parsed") from None
        host = ""
        if isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
            endpoints = payload[0].get("Endpoints")
            if isinstance(endpoints, Mapping):
                docker_endpoint = endpoints.get("docker")
                if isinstance(docker_endpoint, Mapping):
                    candidate = docker_endpoint.get("Host")
                    if isinstance(candidate, str):
                        host = candidate
        if not host.startswith("unix://"):
            raise UnsupportedRuntimeError(
                "the active docker endpoint is not a local Unix socket; remote "
                "contexts are rejected"
            )

    def _daemon_architecture(self, host: str) -> str:
        result = self._spawn(
            ["docker", "info", "--format", "json"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "docker daemon check exceeded its bounded execution time"
            ),
        )
        if result.returncode != 0:
            raise UnsupportedRuntimeError(
                "the docker daemon is unreachable; start the local runtime and retry"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise UnsupportedRuntimeError("docker daemon facts could not be parsed") from None
        if not isinstance(payload, Mapping):
            raise UnsupportedRuntimeError("docker daemon facts could not be parsed")
        if payload.get("OSType") != "linux":
            raise UnsupportedRuntimeError("the docker daemon must run Linux containers")
        raw_arch = payload.get("Architecture")
        arch = _DAEMON_ARCH.get(raw_arch) if isinstance(raw_arch, str) else None
        expected = "amd64" if _CONTAINER_PLATFORM[host] == "linux/amd64" else "arm64"
        if arch != expected:
            raise UnsupportedRuntimeError(
                "the docker daemon architecture does not match the native host "
                "platform; emulated images are not supported"
            )
        return arch

    def _require_compose_capabilities(self) -> None:
        up = self._spawn(
            ["docker", "compose", "up", "--help"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "compose capability check exceeded its bounded execution time"
            ),
        )
        if up.returncode != 0 or "--detach" not in up.stdout or "--pull" not in up.stdout:
            raise UnsupportedRuntimeError("the maintained Compose up options are unavailable")
        ps = self._spawn(
            ["docker", "compose", "ps", "--help"],
            timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            timeout_error=UnsupportedRuntimeError(
                "compose capability check exceeded its bounded execution time"
            ),
        )
        if ps.returncode != 0 or "--format" not in ps.stdout:
            raise UnsupportedRuntimeError("the maintained Compose ps JSON output is unavailable")

    # -- captured JSON state ---------------------------------------------------

    def project_state(self) -> tuple[ServiceState, ...]:
        """Capture exact-project state read-only after asset verification."""
        self.verified_compose_bytes()
        result = self._spawn(
            self._compose_argv("ps", "--all", "--format", "json"),
            timeout_seconds=STATE_COMMAND_TIMEOUT_SECONDS,
            timeout_error=ComposeCommandError(
                "compose state inspection exceeded its bounded execution time " "and was terminated"
            ),
        )
        if result.returncode != 0:
            raise ComposeCommandError("compose state inspection failed; runtime state is unchanged")
        return parse_ps_json(result.stdout)

    # -- ownership, publisher, and port inspection ------------------------------

    def assert_exact_ownership(self, state: Sequence[ServiceState]) -> None:
        """Authorize mutation by exact project ID plus the full fingerprint."""
        for record in state:
            if record.project != self._identity.project_id:
                raise OwnershipConflictError(
                    f"{record.service} belongs to a different Compose project; "
                    "refusing to adopt, stop, or mutate it"
                )
            if record.labels.get(LABEL_WORKSPACE_ID) != self._identity.project_id:
                raise OwnershipConflictError(
                    f"{record.service} lacks the exact workspace identity label; "
                    "refusing to adopt, stop, or mutate it"
                )
            if (
                record.labels.get(LABEL_WORKSPACE_FINGERPRINT)
                != self._identity.workspace_fingerprint
            ):
                raise OwnershipConflictError(
                    "workspace hash collision or drift detected: the full "
                    "fingerprint does not match this workspace; failing closed "
                    "before mutation"
                )

    def assert_no_workspace_path_in_labels(self, state: Sequence[ServiceState]) -> None:
        """Fail closed if any resource metadata exposes the workspace path."""
        canonical = self._identity.canonical_path
        if not canonical:
            return
        for record in state:
            for key, value in record.labels.items():
                if canonical in key or canonical in value:
                    raise OwnershipConflictError(
                        f"{record.service} resource metadata exposes the workspace "
                        "path; refusing unsafe state"
                    )

    def assert_loopback_publishers(self, state: Sequence[ServiceState]) -> None:
        """Fail closed if any captured publisher is not bound to 127.0.0.1."""
        for record in state:
            for publisher in record.publishers:
                if publisher.host_ip != _LOOPBACK_BIND_ADDRESS:
                    raise OwnershipConflictError(
                        f"{record.service} publishes a port on a non-loopback "
                        "address; refusing unsafe state"
                    )

    def preflight_ports(
        self,
        state: Sequence[ServiceState],
        desired_ports: Mapping[DependencyId, int],
    ) -> None:
        """Bind-only port preflight; never sends protocol data or stops owners."""
        for dependency in self._manifest.dependencies:
            port = desired_ports[dependency.id]
            if self._owned_publisher_matches(state, dependency, port):
                continue
            try:
                self._bind_check(dependency.host_bind_address, port)
            except PortConflictError:
                raise PortConflictError(
                    f"{dependency.id.value} desired loopback port {port} is "
                    "unavailable; free the port or change its URL and retry"
                ) from None

    def _owned_publisher_matches(
        self,
        state: Sequence[ServiceState],
        dependency: LocalDependencyDefinition,
        port: int,
    ) -> bool:
        for record in state:
            if record.project != self._identity.project_id:
                continue
            if record.service != dependency.service_name:
                continue
            for publisher in record.publishers:
                if (
                    publisher.host_ip == dependency.host_bind_address
                    and publisher.published_port == port
                    and publisher.target_port == dependency.container_port
                ):
                    return True
        return False

    # -- image pull sequencing and digest verification --------------------------

    def ensure_images(self, runtime: RuntimeFacts) -> tuple[ImagePullRecord, ...]:
        """Pull only missing pinned images, then verify every image identity.

        Each image is inspected locally first; a missing image is pulled with
        its own bounded call (reported per dependency, separately from the
        readiness budget) and re-inspected. Verification requires the reviewed
        index or current-platform child digest plus the native platform.
        """
        records: list[ImagePullRecord] = []
        for dependency in self._manifest.dependencies:
            image = self._inspect_image(dependency)
            pulled = False
            if image is None:
                self._pull_image(dependency)
                image = self._inspect_image(dependency)
                pulled = True
            if image is None:
                raise ImageUnavailableError(
                    f"{dependency.id.value} image is unavailable after pull; "
                    "check registry and disk state"
                )
            self._verify_image_identity(dependency, image, runtime)
            records.append(ImagePullRecord(dependency=dependency.id, pulled=pulled))
        return tuple(records)

    def _inspect_image(self, dependency: LocalDependencyDefinition) -> Mapping[str, Any] | None:
        result = self._spawn(
            ["docker", "image", "inspect", dependency.image_ref, "--format", "json"],
            timeout_seconds=IMAGE_INSPECT_TIMEOUT_SECONDS,
            timeout_error=ImageUnavailableError(
                f"{dependency.id.value} image inspection exceeded its bounded "
                "execution time and was terminated"
            ),
        )
        if result.returncode != 0:
            if "no such" in result.stderr.lower():
                return None
            raise ImageUnavailableError(f"{dependency.id.value} image state could not be inspected")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise ImageUnavailableError(
                f"{dependency.id.value} image inspection was not valid JSON"
            ) from None
        if not isinstance(payload, list) or not payload:
            return None
        image = payload[0]
        if not isinstance(image, Mapping):
            raise ImageUnavailableError(f"{dependency.id.value} image inspection was malformed")
        return image

    def _pull_image(self, dependency: LocalDependencyDefinition) -> None:
        result = self._spawn(
            ["docker", "pull", dependency.image_ref],
            timeout_seconds=self._pull_timeout_seconds,
            timeout_error=ImageUnavailableError(
                f"{dependency.id.value} image pull exceeded its bounded execution "
                "time and was terminated"
            ),
        )
        if result.returncode != 0:
            raise ImageUnavailableError(
                f"{dependency.id.value} image pull failed; check registry access " "and disk space"
            )

    def _verify_image_identity(
        self,
        dependency: LocalDependencyDefinition,
        image: Mapping[str, Any],
        runtime: RuntimeFacts,
    ) -> None:
        expected_arch = "amd64" if runtime.container_platform == "linux/amd64" else "arm64"
        if image.get("Os") != "linux" or image.get("Architecture") != expected_arch:
            raise ImageUnavailableError(
                f"{dependency.id.value} image is not the native "
                f"{runtime.container_platform} variant"
            )
        repo_digests = image.get("RepoDigests")
        if not isinstance(repo_digests, list):
            raise ImageUnavailableError(
                f"{dependency.id.value} image identity could not be verified"
            )
        child_digest = (
            dependency.platform_digests.linux_amd64
            if runtime.container_platform == "linux/amd64"
            else dependency.platform_digests.linux_arm64
        )
        acceptable = {dependency.index_digest, child_digest}
        observed = {
            entry.rsplit("@", 1)[1]
            for entry in repo_digests
            if isinstance(entry, str) and "@" in entry
        }
        if not observed & acceptable:
            raise ImageUnavailableError(
                f"{dependency.id.value} local image identity does not match the " "reviewed digest"
            )

    # -- reconcile ---------------------------------------------------------------

    def reconcile_up(
        self,
        secrets: ComposeSecretSet,
        *,
        timeout_seconds: float,
        derived_env: Mapping[str, str] | None = None,
    ) -> None:
        """Reconcile with verified bytes over stdin; never pulls, bounded.

        ``derived_env`` carries the non-secret derived child variables (user,
        database, host ports) wired from validated configuration by the
        lifecycle orchestrator; it may never override the adapter-owned secret
        or workspace-label variables. The dedicated child-only mapping lives
        only inside this call's child environment and is discarded when the
        call returns. A publish bind race maps to the same ``PORT_CONFLICT``
        category as preflight.
        """
        compose_bytes = self.verified_compose_bytes()
        child_env = self._child_environment(secrets, derived_env)
        result = self._spawn(
            self._compose_argv("up", "--detach", "--pull", "never", with_stdin_file=True),
            timeout_seconds=timeout_seconds,
            input_text=compose_bytes.decode("utf-8"),
            env=child_env,
            timeout_error=ComposeCommandError(
                "compose reconcile exceeded its bounded execution time and was terminated"
            ),
        )
        if result.returncode != 0:
            if _indicates_port_race(result.stderr):
                raise PortConflictError(
                    "a desired loopback port became unavailable during reconcile; "
                    "free the port or change its URL and retry"
                )
            raise ComposeCommandError(
                "compose reconcile failed; project state is retained for inspection"
            )

    def _child_environment(
        self, secrets: ComposeSecretSet, derived_env: Mapping[str, str] | None
    ) -> dict[str, str]:
        reserved = _RESERVED_CHILD_ENV & (derived_env or {}).keys()
        if reserved:
            raise ValueError(
                "derived child variables may not override adapter-owned secret "
                "or workspace-label variables"
            )
        env = dict(self._environ)
        env.update(derived_env or {})
        env.update(secrets.child_mapping())
        env[WORKSPACE_ID_ENV] = self._identity.project_id
        env[WORKSPACE_FINGERPRINT_ENV] = self._identity.workspace_fingerprint
        return env
