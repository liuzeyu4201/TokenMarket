"""Start and stop orchestration for the SF02 local dependency lifecycle.

Implements the ``make dev`` / ``make dev-down`` ordered contracts of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 4, 7, 8, 9, 10 and 11 by composing the reviewed building
blocks (config, identity/lock, Compose adapter, probes, event v2):

1. Effective-mode validation first: only an omitted mode or command-line
   ``mode=local`` is accepted; any other value or origin fails with
   ``INVALID_MODE`` before ``.env.local``, coordination metadata, or Docker is
   touched.
2. ``.env.local`` parse/validation (pure): mode/config rejection precedes the
   lock, coordination, and any Docker access.
3. Canonical workspace identity and the repository-owned manifest (pure), then
   the read-only runtime preflight, exact-project state/ownership/publisher
   inspection, and the no-credential per-dependency port preflight.
4. The per-project non-blocking POSIX lock; configuration, Compose asset,
   endpoint, ownership/state, and ports are revalidated inside it. Any drift
   fails before pull or mutation. Contention rejects with
   ``OPERATION_IN_PROGRESS`` and zero side effects.
5. Per-dependency missing-only image pull plus digest/platform verification,
   reported and timed separately per dependency and entirely *before* the one
   fresh, non-extendable 60-second readiness deadline starts.
6. Reconcile (``up --detach --pull never``, verified bytes over stdin,
   dedicated child-only secret mapping), JSON state collection, and the three
   authenticated probes running concurrently — all bounded by that single
   deadline with no second post-wait budget. Stale evidence can never flip a
   run to success.
7. Per-dependency final evidence plus an aggregate that passes only when all
   three dependencies are freshly ready. Every failure retains all project
   resources and named volumes for inspection; nothing is ever downed,
   stopped, removed, or pruned by the start path, so fixing the cause and
   rerunning converges idempotently on the same owned resources.

Every step emits v2 standard envelopes plus plain-text lines with the same
safe semantics (no secrets, no URLs with user-info, no workspace paths, no raw
subprocess/probe output, no color/icons/animation). All side effects flow
through injected seams so unit tests never touch a real daemon.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..events import DiagnosticCodeV2, emit_event_v2
from .compose import (
    GRAFANA_HOST_PORT_ENV,
    POSTGRES_DB_ENV,
    POSTGRES_HOST_PORT_ENV,
    POSTGRES_USER_ENV,
    REDIS_HOST_PORT_ENV,
    ComposeAdapter,
    ComposeSecretSet,
    ImagePullRecord,
    PortConflictError,
    ResourceKind,
    RuntimeFacts,
    ServiceState,
    build_secret_material,
    build_teardown_placeholders,
)
from .config import (
    InvalidConfigError,
    InvalidModeError,
    LocalEnvironmentConfiguration,
    parse_local_environment,
)
from .identity import (
    ResourceObservation,
    WorkspaceIdentity,
    acquire_project_lock,
    classify_repository_resources,
    ensure_project_runtime_dir,
    secure_runtime_base,
    workspace_identity,
)
from .models import (
    DependencyHealthResult,
    DependencyId,
    InvalidStateTransitionError,
    LifecycleAction,
    LifecycleOperation,
    LifecyclePhase,
    LivenessState,
    LocalDependencyManifest,
    LocalEnvironmentError,
    OperationStatus,
    ProbeKind,
    ReadinessState,
    load_manifest,
)
from .probes import ProbeTarget, probe_dependency

__all__ = [
    "AdapterFactory",
    "ClockFn",
    "ComposeAdapterLike",
    "LifecycleRunOutcome",
    "ProbeFn",
    "SleepFn",
    "start_local_environment",
    "stop_local_environment",
]

ClockFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]
ProbeFn = Callable[[ProbeTarget, float], Awaitable[DependencyHealthResult]]


class ComposeAdapterLike(Protocol):
    """The Compose adapter surface the start orchestration drives."""

    def verify_runtime(self) -> RuntimeFacts: ...

    def verified_compose_bytes(self) -> bytes: ...

    def project_state(self) -> tuple[ServiceState, ...]: ...

    def assert_exact_ownership(self, state: Sequence[ServiceState]) -> None: ...

    def assert_no_workspace_path_in_labels(self, state: Sequence[ServiceState]) -> None: ...

    def assert_loopback_publishers(self, state: Sequence[ServiceState]) -> None: ...

    def preflight_ports(
        self,
        state: Sequence[ServiceState],
        desired_ports: Mapping[DependencyId, int],
    ) -> None: ...

    def ensure_images(self, runtime: RuntimeFacts) -> tuple[ImagePullRecord, ...]: ...

    def reconcile_up(
        self,
        secrets: ComposeSecretSet,
        *,
        timeout_seconds: float,
        derived_env: Mapping[str, str] | None = None,
    ) -> None: ...


AdapterFactory = Callable[
    [LocalDependencyManifest, WorkspaceIdentity, Path, Path], ComposeAdapterLike
]

# Make-origin values that count as an explicit command-line mode selection;
# mirrors the accepted vocabulary of tools/workflow/mode.py.
_COMMAND_LINE_MODE_ORIGINS = frozenset({"command", "command line", "override"})

# Diagnostic codes that the strict v2 payload only allows with a dependency
# field; the aggregate final event (no dependency) degrades them to
# STEP_FAILED while the run outcome keeps the precise code.
_DEPENDENCY_SCOPED_CODES = frozenset(
    {
        DiagnosticCodeV2.IMAGE_UNAVAILABLE.value,
        DiagnosticCodeV2.PORT_CONFLICT.value,
        DiagnosticCodeV2.DEPENDENCY_NOT_READY.value,
    }
)

# Phases that the strict v2 payload only allows with a dependency field.
_DEPENDENCY_SCOPED_PHASES = frozenset(
    {
        LifecyclePhase.IMAGE_PULL,
        LifecyclePhase.IMAGE_VERIFY,
        LifecyclePhase.RECONCILE,
        LifecyclePhase.LIVENESS,
        LifecyclePhase.READINESS,
        LifecyclePhase.STOPPING,
    }
)

_FIRST_STAGE_PROBES: Mapping[DependencyId, ProbeKind] = {
    DependencyId.POSTGRES: ProbeKind.POSTGRES_QUERY,
    DependencyId.REDIS: ProbeKind.REDIS_AUTH_PING,
    DependencyId.GRAFANA: ProbeKind.GRAFANA_HEALTH,
}

# Sub-microsecond remainders cannot perform I/O; treat them as exhausted. This
# never extends the budget or adds a second one (mirrors probes.py).
_MIN_REMAINING_SECONDS = 1e-6


@dataclass(frozen=True)
class LifecycleRunOutcome:
    """The complete evidence of one guarded ``dev`` run.

    ``events`` are v2 standard envelopes; ``plain_lines`` carry the same safe
    payload semantics and correlation ID for NO_COLOR/screen-reader output.
    ``dependency_results`` holds the per-dependency probe evidence of the run
    (empty when the run failed before readiness evidence could exist).
    """

    action: str
    status: str
    diagnostic_code: str
    correlation_id: str
    project_id: str
    message: str
    duration_ms: int
    events: tuple[dict[str, Any], ...]
    plain_lines: tuple[str, ...]
    dependency_results: tuple[DependencyHealthResult, ...]
    # Operation state-machine terminal status when relevant (e.g. INTERRUPTED).
    # Event payload status remains FAILED for interrupts (v2 envelope limit).
    operation_status: str = ""


def _render_plain_line(envelope: Mapping[str, Any]) -> str:
    """Render one v2 envelope as a NO_COLOR-safe, single-line text record."""
    payload = envelope["payload"]
    dependency = payload.get("dependency")
    scope = f" {dependency}" if isinstance(dependency, str) else ""
    return (
        f"[{payload['status']}] {payload['component']} "
        f"{payload['action']}/{payload['phase']}{scope}: "
        f"[{payload['code']}] {payload['message']} "
        f"(duration_ms={payload['duration_ms']}, "
        f"correlation_id={envelope['correlation_id']})"
    )


class _RunEmitter:
    """Paired v2-envelope and plain-text emission for one lifecycle run."""

    def __init__(self, action: str) -> None:
        self.correlation_id = str(uuid.uuid4())
        self.events: list[dict[str, Any]] = []
        self.plain_lines: list[str] = []
        self._action = action

    def emit(
        self,
        *,
        phase: LifecyclePhase,
        status: str,
        code: str,
        message: str,
        duration_ms: int = 0,
        dependency: DependencyId | None = None,
    ) -> None:
        envelope = emit_event_v2(
            action=self._action,
            component="infra" if dependency is not None else "repository",
            phase=phase.value,
            status=status,
            code=DiagnosticCodeV2(code),
            duration_ms=duration_ms,
            message=message,
            correlation_id=self.correlation_id,
            dependency=dependency.value if dependency is not None else None,
        )
        self.events.append(envelope)
        self.plain_lines.append(_render_plain_line(envelope))


def _elapsed_ms(now: ClockFn, started: float) -> int:
    return max(0, int(round((now() - started) * 1000)))


_INTERRUPT_MESSAGE = (
    "lifecycle operation was interrupted; project state and named volumes are "
    "retained for inspection; fix the cause if needed and retry the same command"
)


def _interrupted_outcome(
    *,
    emitter: _RunEmitter,
    action: str,
    project_id: str,
    now: ClockFn,
    started: float,
    phase: LifecyclePhase,
    operation: LifecycleOperation | None,
    keep: bool,
) -> LifecycleRunOutcome:
    """Map KeyboardInterrupt/SIGINT to a safe INTERRUPTED terminal outcome (T077).

    Event payload status remains FAILED (v2 envelope allows only
    STARTED/WAITING/PASSED/FAILED/SKIPPED); the operation state machine uses
    :attr:`OperationStatus.INTERRUPTED`. Resources are retained when any
    mutable work may already have occurred.
    """
    message = _INTERRUPT_MESSAGE
    if not keep:
        message = (
            "lifecycle operation was interrupted before project resources were "
            "mutated; retry the same command"
        )
    interrupted_status = OperationStatus.INTERRUPTED.value
    if operation is not None and not operation.is_terminal:
        try:
            # Immutable transition: retain the returned state for accounting.
            operation = operation.transition(
                OperationStatus.INTERRUPTED,
                phase=phase,
                diagnostic_code=DiagnosticCodeV2.STEP_FAILED.value,
            )
            interrupted_status = operation.status.value
        except InvalidStateTransitionError:
            interrupted_status = (
                operation.status.value if operation is not None else interrupted_status
            )
    event_phase = phase if phase is not LifecyclePhase.STOPPING else LifecyclePhase.FINAL
    if event_phase in _DEPENDENCY_SCOPED_PHASES:
        event_phase = LifecyclePhase.FINAL
    emitter.emit(
        phase=event_phase,
        status="FAILED",
        code=DiagnosticCodeV2.STEP_FAILED.value,
        message=message,
        duration_ms=_elapsed_ms(now, started),
    )
    # Final aggregate for consumers that expect a terminal final event.
    if event_phase is not LifecyclePhase.FINAL:
        emitter.emit(
            phase=LifecyclePhase.FINAL,
            status="FAILED",
            code=DiagnosticCodeV2.STEP_FAILED.value,
            message=message,
            duration_ms=_elapsed_ms(now, started),
        )
    return LifecycleRunOutcome(
        action=action,
        status="FAILED",
        diagnostic_code=DiagnosticCodeV2.STEP_FAILED.value,
        correlation_id=emitter.correlation_id,
        project_id=project_id,
        message=message,
        duration_ms=_elapsed_ms(now, started),
        events=tuple(emitter.events),
        plain_lines=tuple(emitter.plain_lines),
        dependency_results=(),
        operation_status=interrupted_status,
    )


def _validate_effective_mode(mode: str | None, mode_origin: str, *, action: str = "dev") -> None:
    """Accept only an omitted mode or command-line ``mode=local`` (contract).

    Any other value or origin fails closed before ``.env.local``, coordination
    metadata, or Docker is accessed; the file and the shell can never select
    or elevate the effective mode.
    """
    if mode is None or mode == "":
        return
    if mode == "local" and mode_origin in _COMMAND_LINE_MODE_ORIGINS:
        return
    raise InvalidModeError(
        f"make {action} accepts only an omitted mode or an explicit command-line "
        "mode=local; shell, environment, and file origins cannot select or "
        "elevate the lifecycle mode"
    )


def _read_and_parse_config(read_config: Callable[[], str]) -> LocalEnvironmentConfiguration:
    """Read and validate ``.env.local``; unreadable files fail INVALID_CONFIG."""
    try:
        text = read_config()
    except LocalEnvironmentError:
        raise
    except OSError:
        raise InvalidConfigError(
            ".env.local",
            "is required for make dev; copy .env.example, set synthetic "
            "tm_local_ values, and retry",
        ) from None
    return parse_local_environment(text)


def _default_config_reader(repo_root: Path) -> Callable[[], str]:
    path = repo_root / ".env.local"

    def _read() -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            raise InvalidConfigError(
                ".env.local",
                "is required for make dev; copy .env.example, set synthetic "
                "tm_local_ values, and retry",
            ) from None

    return _read


def _default_manifest_loader(repo_root: Path) -> Callable[[], LocalDependencyManifest]:
    path = repo_root / "ops" / "workflow" / "local-dependencies.json"
    return lambda: load_manifest(path)


def _default_adapter_factory(
    manifest: LocalDependencyManifest,
    identity: WorkspaceIdentity,
    project_dir: Path,
    repo_root: Path,
) -> ComposeAdapterLike:
    return ComposeAdapter(
        manifest=manifest,
        identity=identity,
        project_dir=project_dir,
        repo_root=repo_root,
    )


def _default_probe_fn(now: ClockFn, pause: SleepFn) -> ProbeFn:
    async def _probe(target: ProbeTarget, deadline: float) -> DependencyHealthResult:
        return await probe_dependency(target, deadline=deadline, clock=now, sleep=pause)

    return _probe


def _desired_ports(config: LocalEnvironmentConfiguration) -> dict[DependencyId, int]:
    return {connection.dependency_id: connection.host_port for connection in config.connections}


def _postgres_facts(config: LocalEnvironmentConfiguration) -> tuple[str, str]:
    connection = config.connection(DependencyId.POSTGRES)
    username = connection.username
    database = connection.database
    if not isinstance(username, str) or not isinstance(database, str):
        raise LocalEnvironmentError("internal error: postgres connection facts are incomplete")
    return username, database


def _derived_child_env(config: LocalEnvironmentConfiguration) -> dict[str, str]:
    """Non-secret derived Compose child variables from validated configuration."""
    username, database = _postgres_facts(config)
    redis = config.connection(DependencyId.REDIS)
    grafana = config.connection(DependencyId.GRAFANA)
    postgres = config.connection(DependencyId.POSTGRES)
    return {
        POSTGRES_USER_ENV: username,
        POSTGRES_DB_ENV: database,
        POSTGRES_HOST_PORT_ENV: str(postgres.host_port),
        REDIS_HOST_PORT_ENV: str(redis.host_port),
        GRAFANA_HOST_PORT_ENV: str(grafana.host_port),
    }


def _probe_targets(config: LocalEnvironmentConfiguration) -> tuple[ProbeTarget, ...]:
    username, database = _postgres_facts(config)
    postgres = config.connection(DependencyId.POSTGRES)
    redis = config.connection(DependencyId.REDIS)
    grafana = config.connection(DependencyId.GRAFANA)
    db_number = redis.database
    if isinstance(db_number, bool) or not isinstance(db_number, int):
        raise LocalEnvironmentError("internal error: redis connection facts are incomplete")
    return (
        ProbeTarget(
            dependency=DependencyId.POSTGRES,
            host=postgres.host_address,
            port=postgres.host_port,
            username=username,
            database=database,
            secret=postgres.secret,
        ),
        ProbeTarget(
            dependency=DependencyId.REDIS,
            host=redis.host_address,
            port=redis.host_port,
            db_number=db_number,
            secret=redis.secret,
        ),
        ProbeTarget(
            dependency=DependencyId.GRAFANA,
            host=grafana.host_address,
            port=grafana.host_port,
            secret=grafana.secret,
        ),
    )


def _require_deadline(operation: LifecycleOperation) -> float:
    deadline = operation.readiness_deadline
    if deadline is None:
        raise LocalEnvironmentError("internal error: readiness deadline was not started")
    return deadline


def _timeout_results(
    config: LocalEnvironmentConfiguration,
) -> tuple[DependencyHealthResult, ...]:
    """Safe timeout evidence when the shared deadline leaves no probe budget."""
    results = []
    for connection in config.connections:
        dependency = connection.dependency_id
        results.append(
            DependencyHealthResult(
                dependency=dependency,
                liveness=LivenessState.UNKNOWN,
                readiness=ReadinessState.NOT_READY,
                probe=_FIRST_STAGE_PROBES[dependency],
                checked_at=datetime.now(timezone.utc),
                duration_ms=0,
                code=DiagnosticCodeV2.DEPENDENCY_NOT_READY.value,
                safe_reason=(
                    f"{dependency.value} could not be probed before the shared "
                    "readiness deadline was exhausted; inspect the dependency and retry"
                ),
            )
        )
    return tuple(results)


async def _run_probe_batch(
    probe: ProbeFn,
    targets: Sequence[ProbeTarget],
    deadline: float,
    now: ClockFn,
) -> tuple[tuple[DependencyHealthResult, ...], tuple[float, ...]]:
    """Run the three probes concurrently; record each completion timestamp."""

    async def _one(target: ProbeTarget) -> tuple[DependencyHealthResult, float]:
        result = await probe(target, deadline)
        return result, now()

    pairs = await asyncio.gather(*(_one(target) for target in targets))
    return tuple(pair[0] for pair in pairs), tuple(pair[1] for pair in pairs)


def _attribute_port_conflict(
    factory: AdapterFactory,
    manifest: LocalDependencyManifest,
    identity: WorkspaceIdentity,
    project_dir: Path,
    repo_root: Path,
    state: Sequence[ServiceState],
    desired_ports: Mapping[DependencyId, int],
) -> DependencyId | None:
    """Identify which dependency lost a bind race via read-only re-checks."""
    for definition in manifest.dependencies:
        per_dependency = factory(
            replace(manifest, dependencies=(definition,)), identity, project_dir, repo_root
        )
        try:
            per_dependency.preflight_ports(state, desired_ports)
        except PortConflictError:
            return definition.id
    return None


async def start_local_environment(
    *,
    repo_root: Path,
    mode: str | None = None,
    mode_origin: str = "omitted",
    workspace_root: Path | None = None,
    identity: WorkspaceIdentity | None = None,
    config_reader: Callable[[], str] | None = None,
    manifest_loader: Callable[[], LocalDependencyManifest] | None = None,
    runtime_base: Path | None = None,
    adapter_factory: AdapterFactory | None = None,
    probe_fn: ProbeFn | None = None,
    clock: ClockFn | None = None,
    sleep: SleepFn | None = None,
) -> LifecycleRunOutcome:
    """Run the guarded ``make dev`` start lifecycle and return its evidence.

    This is the internal SF02 start orchestration (T031); it is only reached
    through the guarded dispatch (T032) while the public v1 gate stays closed.
    It never raises for contracted failure categories — they are mapped to a
    failed :class:`LifecycleRunOutcome` with stable diagnostics — and it never
    cleans up, stops, or deletes project resources on failure.
    """
    now = time.monotonic if clock is None else clock
    pause = asyncio.sleep if sleep is None else sleep
    action = LifecycleAction.DEV.value
    emitter = _RunEmitter(action)
    started = now()
    project_id = ""
    phase = LifecyclePhase.PREFLIGHT
    current_dependency: DependencyId | None = None
    retained = False
    operation: LifecycleOperation | None = None
    results: tuple[DependencyHealthResult, ...] = ()

    factory = adapter_factory or _default_adapter_factory
    read_config = config_reader or _default_config_reader(repo_root)
    load = manifest_loader or _default_manifest_loader(repo_root)

    def _fail(
        *,
        primary_code: str,
        message: str,
        keep: bool,
        evidence: tuple[DependencyHealthResult, ...] = (),
    ) -> LifecycleRunOutcome:
        aggregate_code = primary_code
        if aggregate_code in _DEPENDENCY_SCOPED_CODES:
            aggregate_code = DiagnosticCodeV2.STEP_FAILED.value
        final_message = message
        if keep:
            final_message += (
                " Project state and named volumes are retained for inspection; "
                "fix the reported cause and retry."
            )
        emitter.emit(
            phase=LifecyclePhase.FINAL,
            status="FAILED",
            code=aggregate_code,
            message=final_message,
            duration_ms=_elapsed_ms(now, started),
        )
        return LifecycleRunOutcome(
            action=action,
            status="FAILED",
            diagnostic_code=primary_code,
            correlation_id=emitter.correlation_id,
            project_id=project_id,
            message=final_message,
            duration_ms=_elapsed_ms(now, started),
            events=tuple(emitter.events),
            plain_lines=tuple(emitter.plain_lines),
            dependency_results=evidence,
        )

    try:
        # 1-2. Effective mode, then pure .env.local validation. Both precede
        # coordination metadata, the lock, and any Docker access.
        _validate_effective_mode(mode, mode_origin)
        config = _read_and_parse_config(read_config)

        # 3. Canonical workspace identity (pure; the path is never emitted).
        resolved_identity = identity or workspace_identity(workspace_root or repo_root)
        project_id = resolved_identity.project_id
        operation = LifecycleOperation(
            correlation_id=emitter.correlation_id,
            action=LifecycleAction.DEV,
            project_id=project_id,
            started_at=started,
        )
        emitter.emit(
            phase=LifecyclePhase.IDENTITY,
            status="PASSED",
            code="OK",
            message=(
                "workspace identity resolved; exact project ownership boundary " f"is {project_id}"
            ),
        )

        # 4. Repository-owned manifest (pure), secure runtime base, adapter.
        manifest = load()
        base = runtime_base if runtime_base is not None else secure_runtime_base()
        project_dir = base / project_id
        adapter = factory(manifest, resolved_identity, project_dir, repo_root)

        # 5-6. Read-only runtime preflight, exact-project state/ownership/
        # publisher inspection, and per-dependency no-credential port checks.
        runtime = adapter.verify_runtime()
        state = adapter.project_state()
        adapter.assert_exact_ownership(state)
        adapter.assert_no_workspace_path_in_labels(state)
        adapter.assert_loopback_publishers(state)
        desired_ports = _desired_ports(config)
        for definition in manifest.dependencies:
            current_dependency = definition.id
            factory(
                replace(manifest, dependencies=(definition,)),
                resolved_identity,
                project_dir,
                repo_root,
            ).preflight_ports(state, desired_ports)
        current_dependency = None
        emitter.emit(
            phase=LifecyclePhase.PREFLIGHT,
            status="PASSED",
            code="OK",
            message=(
                "read-only preflight passed: local configuration, runtime, "
                "ownership, and ports are valid"
            ),
        )

        # 7. Secure runtime directory plus the non-blocking project lock.
        phase = LifecyclePhase.LOCK
        project_runtime_dir = ensure_project_runtime_dir(base, project_id)
        lock = acquire_project_lock(project_runtime_dir, project_id=project_id)
        try:
            # 8. In-lock revalidation closes the preflight race: config,
            # asset, endpoint, ownership/state, and ports may have drifted.
            config = _read_and_parse_config(read_config)
            adapter.verified_compose_bytes()
            runtime = adapter.verify_runtime()
            state = adapter.project_state()
            adapter.assert_exact_ownership(state)
            adapter.assert_no_workspace_path_in_labels(state)
            adapter.assert_loopback_publishers(state)
            desired_ports = _desired_ports(config)
            for definition in manifest.dependencies:
                current_dependency = definition.id
                factory(
                    replace(manifest, dependencies=(definition,)),
                    resolved_identity,
                    project_dir,
                    repo_root,
                ).preflight_ports(state, desired_ports)
            current_dependency = None
            emitter.emit(
                phase=LifecyclePhase.LOCK,
                status="PASSED",
                code="OK",
                message=(
                    "project lock acquired; configuration, asset, endpoint, "
                    "ownership, and ports revalidated"
                ),
            )
            operation = operation.transition(
                OperationStatus.RUNNING, phase=LifecyclePhase.IMAGE_PULL
            )

            # 9. Per-dependency missing-only pull plus digest/platform verify,
            # timed separately per dependency and entirely before the deadline.
            phase = LifecyclePhase.IMAGE_PULL
            for definition in manifest.dependencies:
                current_dependency = definition.id
                per_dependency = factory(
                    replace(manifest, dependencies=(definition,)),
                    resolved_identity,
                    project_dir,
                    repo_root,
                )
                image_started = now()
                records = per_dependency.ensure_images(runtime)
                image_duration = _elapsed_ms(now, image_started)
                record = next(r for r in records if r.dependency is definition.id)
                emitter.emit(
                    phase=LifecyclePhase.IMAGE_PULL,
                    status="PASSED",
                    code="OK",
                    message=(
                        "pulled the reviewed pinned image digest; pull timing "
                        "is reported separately from readiness"
                        if record.pulled
                        else "reviewed image digest already present locally; " "no registry access"
                    ),
                    duration_ms=image_duration,
                    dependency=definition.id,
                )
                emitter.emit(
                    phase=LifecyclePhase.IMAGE_VERIFY,
                    status="PASSED",
                    code="OK",
                    message=(
                        "local image identity matches the reviewed digest and "
                        "the native platform"
                    ),
                    duration_ms=0,
                    dependency=definition.id,
                )
            current_dependency = None

            # 10. One fresh, non-extendable readiness deadline starts only
            # after every image identity is locally available and verified.
            operation = operation.begin_readiness(
                at=now(), budget_seconds=manifest.timeouts.readiness_budget_seconds
            )
            deadline = _require_deadline(operation)
            phase = LifecyclePhase.RECONCILE
            secrets = build_secret_material(
                manifest,
                resolved_identity,
                postgres_password=config.connection(DependencyId.POSTGRES).secret,
                redis_password=config.connection(DependencyId.REDIS).secret,
                grafana_admin_password=config.connection(DependencyId.GRAFANA).secret,
            )
            derived_env = _derived_child_env(config)
            targets = _probe_targets(config)
            completions: tuple[float, ...] = ()
            if deadline - now() <= _MIN_REMAINING_SECONDS:
                # The deadline is exhausted before reconcile; create nothing
                # and classify as a readiness timeout with retained state.
                retained = True
                results = _timeout_results(config)
                completions = tuple(deadline + 1.0 for _ in results)
            else:
                retained = True
                reconcile_started = now()
                try:
                    adapter.reconcile_up(
                        secrets,
                        timeout_seconds=deadline - now(),
                        derived_env=derived_env,
                    )
                except PortConflictError as exc:
                    attributed = _attribute_port_conflict(
                        factory,
                        manifest,
                        resolved_identity,
                        project_dir,
                        repo_root,
                        state,
                        desired_ports,
                    )
                    if attributed is not None:
                        emitter.emit(
                            phase=LifecyclePhase.RECONCILE,
                            status="FAILED",
                            code=DiagnosticCodeV2.PORT_CONFLICT.value,
                            message=exc.message,
                            duration_ms=_elapsed_ms(now, started),
                            dependency=attributed,
                        )
                        if not operation.is_terminal:
                            operation = operation.transition(
                                OperationStatus.FAILED,
                                phase=LifecyclePhase.RECONCILE,
                                diagnostic_code=DiagnosticCodeV2.PORT_CONFLICT.value,
                            )
                        return _fail(
                            primary_code=DiagnosticCodeV2.PORT_CONFLICT.value,
                            message=exc.message,
                            keep=True,
                        )
                    emitter.emit(
                        phase=LifecyclePhase.RECONCILE,
                        status="FAILED",
                        code=DiagnosticCodeV2.STEP_FAILED.value,
                        message=exc.message,
                        duration_ms=_elapsed_ms(now, started),
                    )
                    if not operation.is_terminal:
                        operation = operation.transition(
                            OperationStatus.FAILED,
                            phase=LifecyclePhase.RECONCILE,
                            diagnostic_code=DiagnosticCodeV2.STEP_FAILED.value,
                        )
                    return _fail(
                        primary_code=DiagnosticCodeV2.STEP_FAILED.value,
                        message=exc.message,
                        keep=True,
                    )
                except LocalEnvironmentError as exc:
                    for definition in manifest.dependencies:
                        emitter.emit(
                            phase=LifecyclePhase.RECONCILE,
                            status="FAILED",
                            code=exc.code,
                            message=exc.message,
                            duration_ms=_elapsed_ms(now, started),
                            dependency=definition.id,
                        )
                    if not operation.is_terminal:
                        operation = operation.transition(
                            OperationStatus.FAILED,
                            phase=LifecyclePhase.RECONCILE,
                            diagnostic_code=exc.code,
                        )
                    return _fail(primary_code=exc.code, message=exc.message, keep=True)
                finally:
                    secrets = secrets.release()
                reconcile_duration = _elapsed_ms(now, reconcile_started)
                for definition in manifest.dependencies:
                    emitter.emit(
                        phase=LifecyclePhase.RECONCILE,
                        status="PASSED",
                        code="OK",
                        message=(
                            "compose reconcile converged the exact project "
                            "(up --detach --pull never)"
                        ),
                        duration_ms=reconcile_duration,
                        dependency=definition.id,
                    )

                # 11. Fresh JSON state evidence, then the three authenticated
                # probes concurrently — all within the same deadline.
                if deadline - now() <= _MIN_REMAINING_SECONDS:
                    results = _timeout_results(config)
                    completions = tuple(deadline + 1.0 for _ in results)
                else:
                    state = adapter.project_state()
                    adapter.assert_exact_ownership(state)
                    adapter.assert_loopback_publishers(state)
                    phase = LifecyclePhase.READINESS
                    results, completions = await _run_probe_batch(
                        probe_fn or _default_probe_fn(now, pause), targets, deadline, now
                    )

            # 12. Per-dependency final evidence; only fresh pre-deadline
            # readiness counts, and partial success never passes the aggregate.
            phase = LifecyclePhase.READINESS
            all_ready = True
            for result, completed_at in zip(results, completions):
                fresh = completed_at <= deadline
                ready = result.readiness is ReadinessState.READY and fresh
                if ready:
                    emitter.emit(
                        phase=LifecyclePhase.READINESS,
                        status="PASSED",
                        code="OK",
                        message=(
                            "fresh authenticated readiness evidence " f"({result.probe.value})"
                        ),
                        duration_ms=result.duration_ms,
                        dependency=result.dependency,
                    )
                    continue
                all_ready = False
                reason = result.safe_reason
                if result.readiness is ReadinessState.READY and not fresh:
                    reason = (
                        f"{result.dependency.value} readiness evidence completed "
                        "after the shared readiness deadline; stale evidence "
                        "cannot make the run succeed"
                    )
                emitter.emit(
                    phase=LifecyclePhase.READINESS,
                    status="FAILED",
                    code=DiagnosticCodeV2.DEPENDENCY_NOT_READY.value,
                    message=reason,
                    duration_ms=result.duration_ms,
                    dependency=result.dependency,
                )

            if all_ready:
                operation = operation.transition(
                    OperationStatus.SUCCEEDED, phase=LifecyclePhase.FINAL
                )
                endpoints = config.displayed_endpoints()
                containers = config.displayed_container_endpoints()
                message = (
                    "all three dependencies produced fresh authenticated "
                    "readiness evidence; host endpoints: "
                    f"postgres {endpoints['postgres']}; "
                    f"redis {endpoints['redis']}; "
                    f"grafana {endpoints['grafana']}; "
                    "container endpoints: "
                    f"postgres {containers['postgres']}; "
                    f"redis {containers['redis']}; "
                    f"grafana {containers['grafana']}"
                )
                emitter.emit(
                    phase=LifecyclePhase.FINAL,
                    status="PASSED",
                    code="OK",
                    message=message,
                    duration_ms=_elapsed_ms(now, started),
                )
                return LifecycleRunOutcome(
                    action=action,
                    status="PASSED",
                    diagnostic_code="OK",
                    correlation_id=emitter.correlation_id,
                    project_id=project_id,
                    message=message,
                    duration_ms=_elapsed_ms(now, started),
                    events=tuple(emitter.events),
                    plain_lines=tuple(emitter.plain_lines),
                    dependency_results=results,
                )

            not_ready_message = (
                "one or more dependencies did not produce fresh authenticated "
                "readiness evidence within the shared "
                f"{manifest.timeouts.readiness_budget_seconds}-second deadline"
            )
            if not operation.is_terminal:
                operation = operation.transition(
                    OperationStatus.FAILED,
                    phase=LifecyclePhase.READINESS,
                    diagnostic_code=DiagnosticCodeV2.DEPENDENCY_NOT_READY.value,
                )
            return _fail(
                primary_code=DiagnosticCodeV2.DEPENDENCY_NOT_READY.value,
                message=not_ready_message,
                keep=True,
                evidence=results,
            )
        finally:
            # The lock is held across pull, reconcile, readiness, final state,
            # and final event emission; release is idempotent.
            lock.release()
    except LocalEnvironmentError as exc:
        code = exc.code
        event_phase = phase
        event_dependency = current_dependency
        if event_dependency is None and event_phase in _DEPENDENCY_SCOPED_PHASES:
            # A dependency-scoped phase cannot be emitted without a
            # dependency; degrade the step phase, never the diagnostic code.
            event_phase = LifecyclePhase.FINAL
        event_code = code
        if code in _DEPENDENCY_SCOPED_CODES and event_dependency is None:
            event_code = DiagnosticCodeV2.STEP_FAILED.value
        emitter.emit(
            phase=event_phase,
            status="FAILED",
            code=event_code,
            message=exc.message,
            duration_ms=_elapsed_ms(now, started),
            dependency=event_dependency,
        )
        rejected = (
            phase in (LifecyclePhase.IDENTITY, LifecyclePhase.PREFLIGHT)
            or code == DiagnosticCodeV2.OPERATION_IN_PROGRESS.value
        )
        if operation is not None and not operation.is_terminal:
            operation = operation.transition(
                OperationStatus.REJECTED if rejected else OperationStatus.FAILED,
                phase=phase,
                diagnostic_code=code,
            )
        return _fail(primary_code=code, message=exc.message, keep=retained)
    except KeyboardInterrupt:
        return _interrupted_outcome(
            emitter=emitter,
            action=action,
            project_id=project_id,
            now=now,
            started=started,
            phase=phase,
            operation=operation,
            keep=retained or operation is not None,
        )


def _resource_service(resource: Any) -> str | None:
    """Return the Compose service name for a container resource, if labeled."""
    labels = getattr(resource, "labels", None) or {}
    service = labels.get("com.docker.compose.service")
    return service if isinstance(service, str) and service else None


def _as_resource_observations(resources: Sequence[Any]) -> tuple[ResourceObservation, ...]:
    observations: list[ResourceObservation] = []
    for resource in resources:
        kind = resource.kind
        kind_value = kind.value if isinstance(kind, ResourceKind) else str(kind)
        observations.append(
            ResourceObservation(
                kind=kind_value,
                name=str(resource.name),
                labels=dict(resource.labels),
            )
        )
    return tuple(observations)


def _kind_is(resource: Any, expected: ResourceKind) -> bool:
    kind = resource.kind
    if kind is expected:
        return True
    return str(kind) == expected.value


async def stop_local_environment(
    *,
    repo_root: Path,
    mode: str | None = None,
    mode_origin: str = "omitted",
    workspace_root: Path | None = None,
    identity: WorkspaceIdentity | None = None,
    manifest_loader: Callable[[], LocalDependencyManifest] | None = None,
    runtime_base: Path | None = None,
    adapter_factory: AdapterFactory | None = None,
    clock: ClockFn | None = None,
) -> LifecycleRunOutcome:
    """Run the guarded ``make dev-down`` stop lifecycle and return its evidence.

    Config-free: never requires, parses, or validates ``.env.local``. The
    per-project lock serializes every mutable phase and final event emission
    (T044–T046). Named volumes are retained; moved-workspace resources are
    report-only.
    """
    now = time.monotonic if clock is None else clock
    action = LifecycleAction.DEV_DOWN.value
    emitter = _RunEmitter(action)
    started = now()
    project_id = ""
    phase = LifecyclePhase.IDENTITY
    operation: LifecycleOperation | None = None
    retained = False

    factory = adapter_factory or _default_adapter_factory
    load = manifest_loader or _default_manifest_loader(repo_root)

    def _fail(
        *,
        primary_code: str,
        message: str,
        keep: bool,
    ) -> LifecycleRunOutcome:
        final_message = message
        if keep:
            final_message += (
                " Project state and named volumes are retained for inspection; "
                "fix the reported cause and retry."
            )
        emitter.emit(
            phase=LifecyclePhase.FINAL,
            status="FAILED",
            code=(
                DiagnosticCodeV2.STEP_FAILED.value
                if primary_code in _DEPENDENCY_SCOPED_CODES
                else primary_code
            ),
            message=final_message,
            duration_ms=_elapsed_ms(now, started),
        )
        return LifecycleRunOutcome(
            action=action,
            status="FAILED",
            diagnostic_code=primary_code,
            correlation_id=emitter.correlation_id,
            project_id=project_id,
            message=final_message,
            duration_ms=_elapsed_ms(now, started),
            events=tuple(emitter.events),
            plain_lines=tuple(emitter.plain_lines),
            dependency_results=(),
        )

    try:
        # 1. Effective mode only — no configuration, coordination, or Docker.
        _validate_effective_mode(mode, mode_origin, action="dev-down")

        # 2. Canonical workspace identity (pure; path never emitted).
        resolved_identity = identity or workspace_identity(workspace_root or repo_root)
        project_id = resolved_identity.project_id
        operation = LifecycleOperation(
            correlation_id=emitter.correlation_id,
            action=LifecycleAction.DEV_DOWN,
            project_id=project_id,
            started_at=started,
        )
        emitter.emit(
            phase=LifecyclePhase.IDENTITY,
            status="PASSED",
            code="OK",
            message=(
                "workspace identity resolved; exact project ownership boundary " f"is {project_id}"
            ),
        )

        # 3. Manifest + side-effect-free adapter construction may precede lock.
        manifest = load()
        base = runtime_base if runtime_base is not None else secure_runtime_base()
        project_dir = base / project_id
        adapter = factory(manifest, resolved_identity, project_dir, repo_root)

        # 4. Immediate lock before runtime validation or any Docker access.
        phase = LifecyclePhase.LOCK
        project_runtime_dir = ensure_project_runtime_dir(base, project_id)
        lock = acquire_project_lock(project_runtime_dir, project_id=project_id)
        try:
            emitter.emit(
                phase=LifecyclePhase.LOCK,
                status="PASSED",
                code="OK",
                message="project lock acquired; stop path may proceed",
            )
            operation = operation.transition(OperationStatus.RUNNING, phase=LifecyclePhase.STOPPING)

            # 5. Read-only runtime check, then exact-project discovery.
            phase = LifecyclePhase.PREFLIGHT
            adapter.verify_runtime()
            resources = adapter.project_resources()
            adapter.assert_exact_resource_ownership(resources)

            containers = [r for r in resources if _kind_is(r, ResourceKind.CONTAINER)]
            networks = [r for r in resources if _kind_is(r, ResourceKind.NETWORK)]
            volumes_before = {r.name for r in resources if _kind_is(r, ResourceKind.VOLUME)}

            already_stopped = not containers and not networks
            retained = True
            phase = LifecyclePhase.STOPPING

            if not already_stopped:
                stop_budget = float(manifest.timeouts.stop_operation_seconds)
                remaining = stop_budget - (now() - started)
                if remaining <= 0:
                    return _fail(
                        primary_code=DiagnosticCodeV2.STEP_FAILED.value,
                        message=(
                            "stop operation budget exhausted before reconcile; "
                            "project state is retained for inspection"
                        ),
                        keep=True,
                    )
                placeholders = build_teardown_placeholders(manifest, resolved_identity)
                try:
                    adapter.reconcile_down(placeholders, timeout_seconds=remaining)
                except LocalEnvironmentError as exc:
                    # Per-dependency evidence for remaining containers.
                    remaining_resources = adapter.project_resources()
                    remaining_services = {
                        _resource_service(r)
                        for r in remaining_resources
                        if _kind_is(r, ResourceKind.CONTAINER)
                    }
                    remaining_services.discard(None)
                    if not remaining_services:
                        remaining_services = {dep.value for dep in DependencyId}
                    for dep_name in sorted(s for s in remaining_services if s):
                        try:
                            dependency = DependencyId(dep_name)
                        except ValueError:
                            continue
                        emitter.emit(
                            phase=LifecyclePhase.STOPPING,
                            status="FAILED",
                            code=exc.code,
                            message=exc.message,
                            duration_ms=_elapsed_ms(now, started),
                            dependency=dependency,
                        )
                    if not operation.is_terminal:
                        operation = operation.transition(
                            OperationStatus.FAILED,
                            phase=LifecyclePhase.STOPPING,
                            diagnostic_code=exc.code,
                        )
                    return _fail(primary_code=exc.code, message=exc.message, keep=True)
                finally:
                    placeholders = placeholders.release()

            # 6. Post-stop verification: containers/networks gone, volumes kept.
            after = adapter.project_resources()
            adapter.assert_exact_resource_ownership(after)
            remaining_containers = [r for r in after if _kind_is(r, ResourceKind.CONTAINER)]
            remaining_networks = [r for r in after if _kind_is(r, ResourceKind.NETWORK)]
            volumes_after = {r.name for r in after if _kind_is(r, ResourceKind.VOLUME)}

            if remaining_containers or remaining_networks:
                for resource in remaining_containers:
                    service = _resource_service(resource)
                    if service is None:
                        continue
                    try:
                        dependency = DependencyId(service)
                    except ValueError:
                        continue
                    emitter.emit(
                        phase=LifecyclePhase.STOPPING,
                        status="FAILED",
                        code=DiagnosticCodeV2.STEP_FAILED.value,
                        message=(
                            f"{service} is still present after stop; project "
                            "state is retained for inspection"
                        ),
                        duration_ms=_elapsed_ms(now, started),
                        dependency=dependency,
                    )
                return _fail(
                    primary_code=DiagnosticCodeV2.STEP_FAILED.value,
                    message=(
                        "stop did not clear exact-project containers or networks; "
                        "project state is retained for inspection"
                    ),
                    keep=True,
                )

            # Required named volumes must survive ordinary down.
            expected_volume_suffixes = ("postgres-data", "redis-data")
            for suffix in expected_volume_suffixes:
                expected_name = f"{project_id}_{suffix}"
                # Only require volumes that were present before the stop, or
                # that the project ever owned; a first-time already-stopped
                # environment with no volumes is success, but losing a volume
                # that existed before down is failure.
                if expected_name in volumes_before and expected_name not in volumes_after:
                    return _fail(
                        primary_code=DiagnosticCodeV2.STEP_FAILED.value,
                        message=(
                            f"named volume {suffix} is missing after stop; "
                            "ordinary down must retain every named volume"
                        ),
                        keep=True,
                    )

            # 7. Per-dependency stopping evidence (success path).
            for dependency in (
                DependencyId.POSTGRES,
                DependencyId.REDIS,
                DependencyId.GRAFANA,
            ):
                emitter.emit(
                    phase=LifecyclePhase.STOPPING,
                    status="PASSED",
                    code="OK",
                    message=(
                        f"{dependency.value} runtime instance is stopped; named "
                        "volumes are retained"
                        if not already_stopped
                        else (
                            f"{dependency.value} is already stopped; named " "volumes are retained"
                        )
                    ),
                    duration_ms=_elapsed_ms(now, started),
                    dependency=dependency,
                )

            # 8. Report-only moved-workspace scan (never mutates).
            repository = adapter.repository_resources()
            classification = classify_repository_resources(
                resolved_identity, _as_resource_observations(repository)
            )
            for finding in classification.moved:
                emitter.emit(
                    phase=LifecyclePhase.PREFLIGHT,
                    status="PASSED",
                    code="OK",
                    message=finding.guidance,
                    duration_ms=0,
                )

            if already_stopped:
                message = (
                    "local dependency environment is already stopped; named "
                    "volumes are retained and nothing was mutated"
                )
            else:
                message = (
                    "local dependency runtime instances are stopped; named "
                    "volumes are retained for the next start"
                )
            operation = operation.transition(OperationStatus.SUCCEEDED, phase=LifecyclePhase.FINAL)
            emitter.emit(
                phase=LifecyclePhase.FINAL,
                status="PASSED",
                code="OK",
                message=message,
                duration_ms=_elapsed_ms(now, started),
            )
            return LifecycleRunOutcome(
                action=action,
                status="PASSED",
                diagnostic_code="OK",
                correlation_id=emitter.correlation_id,
                project_id=project_id,
                message=message,
                duration_ms=_elapsed_ms(now, started),
                events=tuple(emitter.events),
                plain_lines=tuple(emitter.plain_lines),
                dependency_results=(),
            )
        finally:
            lock.release()
    except LocalEnvironmentError as exc:
        code = exc.code
        event_phase = phase
        if code == DiagnosticCodeV2.OPERATION_IN_PROGRESS.value:
            event_phase = LifecyclePhase.LOCK
        elif code == DiagnosticCodeV2.INVALID_MODE.value:
            event_phase = LifecyclePhase.PREFLIGHT
        elif event_phase in _DEPENDENCY_SCOPED_PHASES:
            event_phase = LifecyclePhase.FINAL
        event_code = (
            DiagnosticCodeV2.STEP_FAILED.value if code in _DEPENDENCY_SCOPED_CODES else code
        )
        emitter.emit(
            phase=event_phase,
            status="FAILED",
            code=event_code,
            message=exc.message,
            duration_ms=_elapsed_ms(now, started),
        )
        rejected = code in (
            DiagnosticCodeV2.OPERATION_IN_PROGRESS.value,
            DiagnosticCodeV2.INVALID_MODE.value,
        )
        if operation is not None and not operation.is_terminal:
            operation = operation.transition(
                OperationStatus.REJECTED if rejected else OperationStatus.FAILED,
                phase=phase,
                diagnostic_code=code,
            )
        return _fail(primary_code=code, message=exc.message, keep=retained)
    except KeyboardInterrupt:
        return _interrupted_outcome(
            emitter=emitter,
            action=action,
            project_id=project_id,
            now=now,
            started=started,
            phase=phase,
            operation=operation,
            keep=retained or operation is not None,
        )
