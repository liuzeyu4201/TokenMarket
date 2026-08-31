"""Typed entities and manifest validation for the SF02 local environment.

Implements the normative entity and state-machine design of
``specs/002-local-dependency-lifecycle/data-model.md`` and the exact
structural invariants of
``shared/contracts/local-environment/v1/local-dependency-manifest.schema.json``
using only the standard library. Entities are immutable; secret bytes are
excluded from repr, equality, and serialization; and no entity carries raw
workspace paths, URLs with credentials, or raw probe output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn

# ---------------------------------------------------------------------------
# Errors


class LocalEnvironmentError(Exception):
    """Base failure carrying a stable workflow diagnostic code string."""

    code = "STEP_FAILED"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ManifestValidationError(LocalEnvironmentError):
    """The repository-owned dependency manifest violates its reviewed contract."""

    code = "CONTRACT_DRIFT"

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"invalid local dependency manifest at {path}: {reason}")


class OwnershipConflictError(LocalEnvironmentError):
    """A mutation target does not match the owned workspace identity."""

    code = "RESOURCE_OWNERSHIP_CONFLICT"


class OperationInProgressError(LocalEnvironmentError):
    """The per-project lifecycle lock is held by another operation."""

    code = "OPERATION_IN_PROGRESS"


class LockSafetyError(LocalEnvironmentError):
    """Runtime directory or lock storage drifted from its secure contract."""


class InvalidStateTransitionError(LocalEnvironmentError):
    """A lifecycle operation was asked to perform an illegal state transition."""


# ---------------------------------------------------------------------------
# Manifest entities


class DependencyId(str, Enum):
    POSTGRES = "postgres"
    REDIS = "redis"
    GRAFANA = "grafana"


class Durability(str, Enum):
    DURABLE_FACT = "durable-fact"
    PRESERVED_REBUILDABLE = "preserved-rebuildable"
    EPHEMERAL = "ephemeral"


class SecretTransport(str, Enum):
    POSTGRES_PASSWORD_FILE = "postgres-password-file"
    REDIS_CONFIG_FILE = "redis-config-file"
    GRAFANA_ADMIN_PASSWORD_FILE = "grafana-admin-password-file"


@dataclass(frozen=True)
class PlatformDigests:
    """Reviewed per-platform child digests of one multi-platform OCI index."""

    linux_amd64: str
    linux_arm64: str


@dataclass(frozen=True)
class NamedVolumeDefinition:
    logical_name: str
    mount_path: str
    delete_on_down: bool = False


@dataclass(frozen=True)
class EphemeralStorageDefinition:
    type: str
    mount_path: str
    owner_policy: str
    mode: str


@dataclass(frozen=True)
class LocalDependencyDefinition:
    """One and only one required dependency from the reviewed manifest."""

    id: DependencyId
    repository: str
    version_tag: str
    index_digest: str
    platform_digests: PlatformDigests
    required_platforms: tuple[str, ...]
    service_name: str
    host_url_field: str
    container_port: int
    default_host_port: int
    host_bind_address: str
    liveness_probe: str
    readiness_probe: str
    durability: Durability
    secret_transport: SecretTransport
    volume: NamedVolumeDefinition | None
    ephemeral_storage: EphemeralStorageDefinition | None
    runtime_uid: int
    runtime_gid: int
    runtime_uid_policy: str
    stop_grace_period_seconds: int

    @property
    def image_ref(self) -> str:
        """Immutable ``repository:tag@index-digest`` reference Compose consumes."""
        return f"{self.repository}:{self.version_tag}@{self.index_digest}"


@dataclass(frozen=True)
class ManifestProject:
    prefix: str
    workspace_hash_algorithm: str
    workspace_hash_length: int
    workspace_fingerprint_length: int
    compose_file: str
    compose_transport: str
    compose_project_directory_policy: str
    lock_mechanism: str


@dataclass(frozen=True)
class ManifestRuntime:
    docker_version: str
    compose_version: str
    endpoint: str
    secret_transport: str
    hosts: tuple[str, ...]


@dataclass(frozen=True)
class ManifestTimeouts:
    readiness_budget_seconds: int
    repeat_confirmation_seconds: int
    stop_operation_seconds: int


@dataclass(frozen=True)
class LocalDependencyManifest:
    """Repository-owned source of truth for the SF02 dependency set."""

    schema_version: str
    diagnostic_contract_version: str
    project: ManifestProject
    runtime: ManifestRuntime
    timeouts: ManifestTimeouts
    dependencies: tuple[LocalDependencyDefinition, ...]

    def dependency(self, dependency_id: DependencyId) -> LocalDependencyDefinition:
        """Return the single definition for one required dependency."""
        for definition in self.dependencies:
            if definition.id == dependency_id:
                return definition
        raise KeyError(dependency_id)


# ---------------------------------------------------------------------------
# Lifecycle operation entity and state machine


class LifecycleAction(str, Enum):
    DEV = "dev"
    DEV_DOWN = "dev-down"


class LifecyclePhase(str, Enum):
    IDENTITY = "identity"
    LOCK = "lock"
    PREFLIGHT = "preflight"
    IMAGE_PULL = "image-pull"
    IMAGE_VERIFY = "image-verify"
    RECONCILE = "reconcile"
    LIVENESS = "liveness"
    READINESS = "readiness"
    STOPPING = "stopping"
    FINAL = "final"


class OperationStatus(str, Enum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    REJECTED = "REJECTED"


_TERMINAL_STATUSES = frozenset(
    {
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.INTERRUPTED,
        OperationStatus.REJECTED,
    }
)

# Contracted lifecycle state machine (data-model.md): preflight rejection and
# lock contention resolve REQUESTED directly; only a RUNNING operation may
# succeed, fail after mutation, or be interrupted. Terminal states never move.
_ALLOWED_TRANSITIONS: Mapping[OperationStatus, frozenset[OperationStatus]] = {
    OperationStatus.REQUESTED: frozenset(
        {
            OperationStatus.RUNNING,
            OperationStatus.FAILED,
            OperationStatus.INTERRUPTED,
            OperationStatus.REJECTED,
        }
    ),
    OperationStatus.RUNNING: frozenset(
        {
            OperationStatus.SUCCEEDED,
            OperationStatus.FAILED,
            OperationStatus.INTERRUPTED,
        }
    ),
    OperationStatus.SUCCEEDED: frozenset(),
    OperationStatus.FAILED: frozenset(),
    OperationStatus.INTERRUPTED: frozenset(),
    OperationStatus.REJECTED: frozenset(),
}


@dataclass(frozen=True)
class LifecycleOperation:
    """One ``make dev`` or ``make dev-down`` run.

    ``started_at``/``readiness_*`` are monotonic-clock seconds, never wall
    time; the readiness deadline is set exactly once and cannot be extended.
    """

    correlation_id: str
    action: LifecycleAction
    project_id: str
    started_at: float
    phase: LifecyclePhase = LifecyclePhase.IDENTITY
    status: OperationStatus = OperationStatus.REQUESTED
    readiness_started_at: float | None = None
    readiness_deadline: float | None = None
    duration_ms: int = 0
    diagnostic_code: str = "OK"

    def __post_init__(self) -> None:
        if not self.correlation_id:
            raise ValueError("correlation_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if (self.readiness_started_at is None) != (self.readiness_deadline is None):
            raise ValueError("readiness start and deadline must be set together")
        if self.readiness_deadline is not None and self.readiness_started_at is not None:
            if self.readiness_deadline < self.readiness_started_at:
                raise ValueError("readiness deadline must not precede its start")

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def transition(
        self,
        status: OperationStatus,
        *,
        phase: LifecyclePhase | None = None,
        diagnostic_code: str | None = None,
        duration_ms: int | None = None,
    ) -> LifecycleOperation:
        """Return the next immutable state or raise on an illegal transition."""
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(
                f"lifecycle transition {self.status.value} -> {status.value} is not allowed"
            )
        return replace(
            self,
            status=status,
            phase=self.phase if phase is None else phase,
            diagnostic_code=(self.diagnostic_code if diagnostic_code is None else diagnostic_code),
            duration_ms=self.duration_ms if duration_ms is None else duration_ms,
        )

    def begin_readiness(self, *, at: float, budget_seconds: int) -> LifecycleOperation:
        """Start the single non-extendable readiness deadline."""
        if self.readiness_deadline is not None:
            raise InvalidStateTransitionError(
                "readiness deadline already started and cannot be extended"
            )
        if budget_seconds <= 0:
            raise ValueError("readiness budget must be positive")
        return replace(
            self,
            readiness_started_at=at,
            readiness_deadline=at + budget_seconds,
        )

    def remaining_readiness_seconds(self, at: float) -> float | None:
        """Remaining deadline budget; negative once the deadline has passed."""
        if self.readiness_deadline is None:
            return None
        return self.readiness_deadline - at


# ---------------------------------------------------------------------------
# Dependency instance and health evidence


class InstanceState(str, Enum):
    ABSENT = "ABSENT"
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    EXITED = "EXITED"
    UNKNOWN = "UNKNOWN"


class InstanceHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"


@dataclass(frozen=True)
class DependencyInstance:
    """Observed reconciled state of one definition in one project."""

    dependency_id: DependencyId
    container_id: str | None = None
    image_digest: str | None = None
    image_matches_desired: bool = False
    state: InstanceState = InstanceState.ABSENT
    health: InstanceHealth = InstanceHealth.UNKNOWN
    published_port: int | None = None
    owner_labels_valid: bool = False
    volume_attached: bool = False

    def __post_init__(self) -> None:
        if self.published_port is not None and not 1 <= self.published_port <= 65535:
            raise ValueError("published_port must be within 1..65535")

    def authorize_mutation(self) -> None:
        """Fail closed unless exact project/fingerprint owner labels verified."""
        if not self.owner_labels_valid:
            raise OwnershipConflictError(
                f"{self.dependency_id.value} instance lacks exact project/fingerprint "
                "ownership labels; refusing to adopt, mutate, or reuse it"
            )


class LivenessState(str, Enum):
    ALIVE = "alive"
    NOT_ALIVE = "not_alive"
    UNKNOWN = "unknown"


class ReadinessState(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    WAITING = "waiting"


class ProbeKind(str, Enum):
    POSTGRES_QUERY = "postgres-query"
    REDIS_AUTH_PING = "redis-auth-ping"
    GRAFANA_HEALTH = "grafana-health"
    GRAFANA_ADMIN = "grafana-admin"


SAFE_REASON_MAX_LENGTH = 200


@dataclass(frozen=True)
class DependencyHealthResult:
    """Short-lived, single-operation probe evidence; never raw probe output."""

    dependency: DependencyId
    liveness: LivenessState
    readiness: ReadinessState
    probe: ProbeKind
    checked_at: datetime
    duration_ms: int
    code: str = "OK"
    safe_reason: str = ""

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        offset = self.checked_at.utcoffset()
        if offset is None:
            raise ValueError("checked_at must be timezone-aware UTC")
        if offset != timedelta(0):
            raise ValueError("checked_at must be UTC")
        if not self.code:
            raise ValueError("a stable diagnostic code is required")
        if len(self.safe_reason) > SAFE_REASON_MAX_LENGTH:
            raise ValueError(
                f"safe_reason must stay within {SAFE_REASON_MAX_LENGTH} bounded characters"
            )


# ---------------------------------------------------------------------------
# Compose secret material (secret bytes excluded from repr/equality)


class SecretPurpose(str, Enum):
    POSTGRES_PASSWORD = "postgres-password"
    REDIS_CONFIG = "redis-config"
    GRAFANA_ADMIN_PASSWORD = "grafana-admin-password"
    TEARDOWN_PLACEHOLDER = "teardown-placeholder"


class SecretCleanupState(str, Enum):
    IN_MEMORY = "in-memory"
    RELEASED = "released"
    CONTAINER_REMOVED = "container-removed"


_SOURCE_FIELD_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class ComposeSecretMaterial:
    """One dedicated Compose child-environment secret mapping.

    ``secret`` bytes are excluded from repr, equality, hash, and any
    serialization; ``source_field`` carries the configuration field *name*
    only, never a value.
    """

    project_id: str
    purpose: SecretPurpose
    source_field: str
    container_owner_uid: int
    container_owner_gid: int
    secret: str = field(default="", repr=False, compare=False)
    container_file_mode: str = "0400"
    cleanup_state: SecretCleanupState = SecretCleanupState.IN_MEMORY

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("project_id is required")
        if not _SOURCE_FIELD_PATTERN.fullmatch(self.source_field):
            raise ValueError("source_field must be a configuration field name, never a value")
        if self.container_owner_uid < 1 or self.container_owner_gid < 1:
            raise ValueError("container secret owner must be a verified non-root UID/GID")
        if self.container_file_mode != "0400":
            raise ValueError("container secret files must be mode 0400")
        if self.cleanup_state == SecretCleanupState.IN_MEMORY and not self.secret:
            raise ValueError("an in-memory secret mapping requires secret bytes")
        if self.cleanup_state != SecretCleanupState.IN_MEMORY and self.secret:
            raise ValueError("released secret bytes must be dropped, not retained")

    def release(self) -> ComposeSecretMaterial:
        """Drop the secret bytes after the Compose child process has ended."""
        return replace(self, secret="", cleanup_state=SecretCleanupState.RELEASED)

    def container_removed(self) -> ComposeSecretMaterial:
        """Record that the Compose-mounted file disappeared with its container."""
        return replace(self, secret="", cleanup_state=SecretCleanupState.CONTAINER_REMOVED)


# ---------------------------------------------------------------------------
# API/Billing service readiness projection


class ReadinessService(str, Enum):
    API_SERVICE = "api-service"
    BILLING_SERVICE = "billing-service"


class ServiceReadinessStatus(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"


@dataclass(frozen=True)
class ServiceDependencyResult:
    """One failed-dependency entry; only safe fields may be serialized."""

    name: DependencyId
    status: ServiceReadinessStatus
    code: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("a stable safe code is required")

    def to_dict(self) -> dict[str, str]:
        """Serialize exactly the contracted safe fields and nothing else."""
        return {"name": self.name.value, "status": self.status.value, "code": self.code}


@dataclass(frozen=True)
class ServiceReadinessResult:
    """API/Billing readiness response projection (SF02: PostgreSQL only)."""

    service: ReadinessService
    status: ServiceReadinessStatus
    version: str
    request_id: str
    http_status: int
    dependencies: tuple[ServiceDependencyResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("version is required")
        if not self.request_id:
            raise ValueError("request_id is required")
        if self.status == ServiceReadinessStatus.READY:
            if self.http_status != 200:
                raise ValueError("a ready result must use HTTP 200")
            if self.dependencies:
                raise ValueError("a ready result carries no dependency entries")
        else:
            if self.http_status != 503:
                raise ValueError("a not_ready result must use HTTP 503")
            if len(self.dependencies) != 1:
                raise ValueError("SF02 reports exactly one PostgreSQL dependency result")
            entry = self.dependencies[0]
            if entry.name != DependencyId.POSTGRES:
                raise ValueError("SF02 readiness tracks only the postgres dependency")
            if entry.status != ServiceReadinessStatus.NOT_READY:
                raise ValueError("a failed readiness dependency must be not_ready")


# ---------------------------------------------------------------------------
# Exact structural manifest validation (schema is const-heavy and fixed)


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_PREFIX_LENGTH = len("sha256:")
_REQUIRED_PLATFORMS = ("linux/amd64", "linux/arm64")
_DEPENDENCY_ORDER = ("postgres", "redis", "grafana")

_TOP_LEVEL_KEYS = {
    "schema_version",
    "diagnostic_contract_version",
    "project",
    "runtime",
    "timeouts",
    "dependencies",
}
_PROJECT_CONSTS: Mapping[str, Any] = {
    "prefix": "tokenmarket",
    "workspace_hash_algorithm": "sha256-canonical-path-nfc-utf8",
    "workspace_hash_length": 12,
    "workspace_fingerprint_length": 64,
    "compose_file": "infra/docker/compose.local.yml",
    "compose_transport": "verified-committed-bytes-via-stdin",
    "compose_project_directory_policy": "secure-runtime-project-id-directory",
    "lock_mechanism": "posix-fcntl-nonblocking-exclusive",
}
_RUNTIME_CONSTS: Mapping[str, Any] = {
    "docker_version": "29.5.3",
    "compose_version": "5.1.4",
    "endpoint": "local-unix-socket",
    "secret_transport": "compose-environment-source-secret-files",
}
_TIMEOUT_CONSTS: Mapping[str, Any] = {
    "readiness_budget_seconds": 60,
    "repeat_confirmation_seconds": 15,
    "stop_operation_seconds": 75,
}

_DEPENDENCY_REQUIRED_KEYS = {
    "id",
    "repository",
    "version_tag",
    "index_digest",
    "platform_digests",
    "required_platforms",
    "service_name",
    "host_url_field",
    "container_port",
    "default_host_port",
    "host_bind_address",
    "liveness_probe",
    "readiness_probe",
    "durability",
    "secret_transport",
    "runtime_uid",
    "runtime_gid",
    "runtime_uid_policy",
    "stop_grace_period_seconds",
}
_DEPENDENCY_OPTIONAL_KEYS = {"volume", "ephemeral_storage"}

_DEPENDENCY_CONSTS: Mapping[str, Mapping[str, Any]] = {
    "postgres": {
        "repository": "docker.io/library/postgres",
        "version_tag": "15.18-bookworm",
        "service_name": "postgres",
        "host_url_field": "DATABASE_URL",
        "container_port": 5432,
        "default_host_port": 5432,
        "liveness_probe": "pg-isready-tcp",
        "readiness_probe": "authenticated-select-1",
        "durability": "durable-fact",
        "secret_transport": "postgres-password-file",
        "stop_grace_period_seconds": 60,
    },
    "redis": {
        "repository": "docker.io/library/redis",
        "version_tag": "7.2.14-bookworm",
        "service_name": "redis",
        "host_url_field": "REDIS_URL",
        "container_port": 6379,
        "default_host_port": 6379,
        "liveness_probe": "redis-process",
        "readiness_probe": "authenticated-ping-pong",
        "durability": "preserved-rebuildable",
        "secret_transport": "redis-config-file",
        "stop_grace_period_seconds": 30,
    },
    "grafana": {
        "repository": "docker.io/grafana/grafana",
        "version_tag": "13.0.3",
        "service_name": "grafana",
        "host_url_field": "GRAFANA_URL",
        "container_port": 3000,
        "default_host_port": 3000,
        "liveness_probe": "grafana-api-health",
        "readiness_probe": "health-database-ok-and-admin-user",
        "durability": "ephemeral",
        "secret_transport": "grafana-admin-password-file",
        "stop_grace_period_seconds": 30,
    },
}
_VOLUME_CONSTS: Mapping[str, tuple[str, str]] = {
    "postgres": ("postgres-data", "/var/lib/postgresql/data"),
    "redis": ("redis-data", "/data"),
}


def _fail(path: str, reason: str) -> NoReturn:
    raise ManifestValidationError(path, reason)


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, f"expected an object, got {type(value).__name__}")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    extra = set(value.keys()) - required - optional
    if missing:
        first = sorted(missing)[0]
        _fail(
            f"{path}.{first}",
            f"missing required field(s): {', '.join(sorted(missing))}",
        )
    if extra:
        _fail(path, f"unexpected field(s): {', '.join(sorted(extra))}")


def _const(value: Mapping[str, Any], key: str, expected: Any, path: str) -> Any:
    if key not in value:
        _fail(f"{path}.{key}", f"missing required field; must be exactly {expected!r}")
    actual = value[key]
    if type(actual) is not type(expected) or actual != expected:
        _fail(f"{path}.{key}", f"must be exactly {expected!r}")
    return actual


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        _fail(
            path,
            "must match ^sha256:[0-9a-f]{64}$ (reviewed immutable digest required)",
        )
    hex_part = value[_SHA256_PREFIX_LENGTH:]
    if len(set(hex_part)) == 1:
        _fail(
            path,
            "degenerate single-nibble digest is a placeholder, not a reviewed digest",
        )
    return value


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, f"must be an integer, got {type(value).__name__}")
    if value < 1:
        _fail(path, "must be a positive integer (>= 1)")
    return int(value)


def _parse_volume(value: Any, path: str, dependency_id: str) -> NamedVolumeDefinition:
    volume = _as_mapping(value, path)
    _exact_keys(volume, path, required={"logical_name", "mount_path", "delete_on_down"})
    logical_name, mount_path = _VOLUME_CONSTS[dependency_id]
    _const(volume, "logical_name", logical_name, path)
    _const(volume, "mount_path", mount_path, path)
    _const(volume, "delete_on_down", False, path)
    return NamedVolumeDefinition(
        logical_name=logical_name,
        mount_path=mount_path,
        delete_on_down=False,
    )


def _parse_ephemeral_storage(value: Any, path: str) -> EphemeralStorageDefinition:
    storage = _as_mapping(value, path)
    _exact_keys(storage, path, required={"type", "mount_path", "owner_policy", "mode"})
    _const(storage, "type", "tmpfs", path)
    _const(storage, "mount_path", "/var/lib/grafana", path)
    _const(storage, "owner_policy", "verified-runtime-uid-gid", path)
    _const(storage, "mode", "0700", path)
    return EphemeralStorageDefinition(
        type="tmpfs",
        mount_path="/var/lib/grafana",
        owner_policy="verified-runtime-uid-gid",
        mode="0700",
    )


def _parse_dependency(value: Any, index: int, expected_id: str) -> LocalDependencyDefinition:
    path = f"$.dependencies[{index}]"
    dependency = _as_mapping(value, path)
    _exact_keys(
        dependency,
        path,
        required=set(_DEPENDENCY_REQUIRED_KEYS),
        optional=set(_DEPENDENCY_OPTIONAL_KEYS),
    )
    _const(dependency, "id", expected_id, path)
    consts = _DEPENDENCY_CONSTS[expected_id]
    for key, expected in consts.items():
        _const(dependency, key, expected, path)
    _const(dependency, "host_bind_address", "127.0.0.1", path)
    _const(
        dependency,
        "runtime_uid_policy",
        "verified-upstream-non-root-secret-owner",
        path,
    )

    index_digest = _digest(dependency["index_digest"], f"{path}.index_digest")
    platform_map = _as_mapping(dependency["platform_digests"], f"{path}.platform_digests")
    _exact_keys(
        platform_map,
        f"{path}.platform_digests",
        required={"linux_amd64", "linux_arm64"},
    )
    linux_amd64 = _digest(platform_map["linux_amd64"], f"{path}.platform_digests.linux_amd64")
    linux_arm64 = _digest(platform_map["linux_arm64"], f"{path}.platform_digests.linux_arm64")
    if index_digest in (linux_amd64, linux_arm64):
        _fail(
            f"{path}.index_digest",
            "leaf-only identity: index_digest must reference the reviewed "
            "multi-platform index, not a platform child",
        )

    platforms = dependency["required_platforms"]
    if not isinstance(platforms, list) or tuple(platforms) != _REQUIRED_PLATFORMS:
        _fail(
            f"{path}.required_platforms",
            "must be exactly ['linux/amd64', 'linux/arm64'] in schema order",
        )

    runtime_uid = _positive_int(dependency["runtime_uid"], f"{path}.runtime_uid")
    runtime_gid = _positive_int(dependency["runtime_gid"], f"{path}.runtime_gid")

    volume: NamedVolumeDefinition | None = None
    ephemeral: EphemeralStorageDefinition | None = None
    if expected_id in ("postgres", "redis"):
        if "ephemeral_storage" in dependency:
            _fail(
                path,
                f"{expected_id} must declare a named volume, not ephemeral storage",
            )
        if "volume" not in dependency:
            _fail(f"{path}.volume", f"{expected_id} requires a named volume definition")
        volume = _parse_volume(dependency["volume"], f"{path}.volume", expected_id)
    else:
        if "volume" in dependency:
            _fail(path, "grafana must declare tmpfs ephemeral storage, not a named volume")
        if "ephemeral_storage" not in dependency:
            _fail(
                f"{path}.ephemeral_storage",
                "grafana requires an explicit tmpfs ephemeral storage definition",
            )
        ephemeral = _parse_ephemeral_storage(
            dependency["ephemeral_storage"], f"{path}.ephemeral_storage"
        )

    return LocalDependencyDefinition(
        id=DependencyId(expected_id),
        repository=consts["repository"],
        version_tag=consts["version_tag"],
        index_digest=index_digest,
        platform_digests=PlatformDigests(linux_amd64=linux_amd64, linux_arm64=linux_arm64),
        required_platforms=_REQUIRED_PLATFORMS,
        service_name=consts["service_name"],
        host_url_field=consts["host_url_field"],
        container_port=consts["container_port"],
        default_host_port=consts["default_host_port"],
        host_bind_address="127.0.0.1",
        liveness_probe=consts["liveness_probe"],
        readiness_probe=consts["readiness_probe"],
        durability=Durability(consts["durability"]),
        secret_transport=SecretTransport(consts["secret_transport"]),
        volume=volume,
        ephemeral_storage=ephemeral,
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        runtime_uid_policy="verified-upstream-non-root-secret-owner",
        stop_grace_period_seconds=consts["stop_grace_period_seconds"],
    )


def parse_manifest(data: Any) -> LocalDependencyManifest:
    """Validate manifest-shaped data against the exact reviewed contract."""
    root = _as_mapping(data, "$")
    _exact_keys(root, "$", required=set(_TOP_LEVEL_KEYS))
    _const(root, "schema_version", "1.0.0", "$")
    _const(root, "diagnostic_contract_version", "2.0.0", "$")

    project = _as_mapping(root["project"], "$.project")
    _exact_keys(project, "$.project", required=set(_PROJECT_CONSTS.keys()))
    for key, expected in _PROJECT_CONSTS.items():
        _const(project, key, expected, "$.project")

    runtime = _as_mapping(root["runtime"], "$.runtime")
    _exact_keys(runtime, "$.runtime", required=set(_RUNTIME_CONSTS.keys()) | {"hosts"})
    for key, expected in _RUNTIME_CONSTS.items():
        _const(runtime, key, expected, "$.runtime")
    hosts = runtime["hosts"]
    if not isinstance(hosts, list) or tuple(hosts) != ("darwin/arm64", "linux/amd64"):
        _fail(
            "$.runtime.hosts",
            "must be exactly ['darwin/arm64', 'linux/amd64'] in order",
        )

    timeouts = _as_mapping(root["timeouts"], "$.timeouts")
    _exact_keys(timeouts, "$.timeouts", required=set(_TIMEOUT_CONSTS.keys()))
    for key, expected in _TIMEOUT_CONSTS.items():
        _const(timeouts, key, expected, "$.timeouts")

    raw_dependencies = root["dependencies"]
    if not isinstance(raw_dependencies, list) or len(raw_dependencies) != len(_DEPENDENCY_ORDER):
        _fail(
            "$.dependencies",
            "must contain exactly postgres, redis, grafana in schema order",
        )
    dependencies = tuple(
        _parse_dependency(value, index, expected_id)
        for index, (value, expected_id) in enumerate(zip(raw_dependencies, _DEPENDENCY_ORDER))
    )

    return LocalDependencyManifest(
        schema_version="1.0.0",
        diagnostic_contract_version="2.0.0",
        project=ManifestProject(
            prefix="tokenmarket",
            workspace_hash_algorithm="sha256-canonical-path-nfc-utf8",
            workspace_hash_length=12,
            workspace_fingerprint_length=64,
            compose_file="infra/docker/compose.local.yml",
            compose_transport="verified-committed-bytes-via-stdin",
            compose_project_directory_policy="secure-runtime-project-id-directory",
            lock_mechanism="posix-fcntl-nonblocking-exclusive",
        ),
        runtime=ManifestRuntime(
            docker_version="29.5.3",
            compose_version="5.1.4",
            endpoint="local-unix-socket",
            secret_transport="compose-environment-source-secret-files",
            hosts=("darwin/arm64", "linux/amd64"),
        ),
        timeouts=ManifestTimeouts(
            readiness_budget_seconds=60,
            repeat_confirmation_seconds=15,
            stop_operation_seconds=75,
        ),
        dependencies=dependencies,
    )


def load_manifest(path: Path) -> LocalDependencyManifest:
    """Load and validate a manifest JSON document from the repository."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data: Any = json.load(handle)
    except OSError as exc:
        raise ManifestValidationError("$", f"manifest unreadable: {type(exc).__name__}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestValidationError("$", f"manifest is not valid JSON: {exc.msg}") from exc
    return parse_manifest(data)
