"""Lifecycle dev-down orchestration tests for the SF02 local environment (T038, US2).

Covers the ``make dev-down`` ordered contract in
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 7, 8 and 11 using only fake seams — no real Docker
daemon, sockets, or network:

- identity resolution BEFORE any configuration read: down works with
  ``.env.local`` moved aside and never requires, parses, or validates it;
  the stop entry point has no configuration input at all.
- the per-project POSIX lock is acquired immediately after identity, before
  runtime validation or any Docker access; contention rejects with
  ``OPERATION_IN_PROGRESS`` and zero side effects (T046).
- discovery and graceful stop: exact-project containers/orphan networks are
  reconciled, named volumes are verified retained, the stop call is bounded
  by the 75-second stop budget, and the already-stopped volume-only state is
  an idempotent success.
- partial failure retains state with per-dependency evidence, a fixed rerun
  converges, a lost named volume fails closed, and resources of a moved old
  workspace are mandatory report-only findings with safe recovery direction.
- final per-dependency v2 standard-envelope events plus an aggregate, all
  redacted and NO_COLOR-safe; T049's guarded dispatch runs the same
  orchestration while the public target stays fail-closed.

Every identity uses the disjoint ``tmtest-`` test prefix so fakes can never
address a developer project. These tests fail until T043/T044 implement the
down surface in ``tools/workflow/local_env/compose.py`` and
``tools/workflow/local_env/lifecycle.py`` (dispatch: T049).
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
from pathlib import Path
from typing import Any, Mapping

import pytest

from workflow.local_env import compose as compose_module
from workflow.local_env import identity as identity_module
from workflow.local_env import models as models_module

from .conftest import TEST_REPOSITORY_LABEL, MonotonicClock, assert_not_developer_project
from .helpers import load_json, validate_event_v2

SENTINEL_WORKSPACE_PATH = "/sf02-down-test-workspace"
INERT_REPO_ROOT = Path("/sf02-down-test-repo")
OLD_WORKSPACE_PROJECT_ID = "tokenmarket-aaaa1111bbbb"

_DOCKER_CALLS = frozenset(
    {
        "verify_runtime",
        "project_resources",
        "repository_resources",
        "reconcile_down",
        "remove_exact_resources",
    }
)


def _lifecycle() -> Any:
    lifecycle = importlib.import_module("workflow.local_env.lifecycle")
    if not hasattr(lifecycle, "stop_local_environment"):
        pytest.fail(
            "workflow.local_env.lifecycle.stop_local_environment is not " "implemented yet (T044)"
        )
    return lifecycle


# ---------------------------------------------------------------------------
# Fixtures and scripted fakes


@pytest.fixture(scope="module")
def manifest() -> Any:
    return models_module.parse_manifest(load_json("ops", "workflow", "local-dependencies.json"))


@pytest.fixture
def identity(test_project_identity: Any) -> Any:
    assert_not_developer_project(test_project_identity.project_id)
    return identity_module.WorkspaceIdentity(
        workspace_hash=test_project_identity.project_id.removeprefix("tmtest-"),
        workspace_fingerprint=test_project_identity.workspace_fingerprint,
        project_id=test_project_identity.project_id,
        canonical_path=SENTINEL_WORKSPACE_PATH,
    )


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


class FakeResource:
    """Duck-typed exact-label resource record (compose.ProjectResource shape)."""

    def __init__(
        self,
        kind: str,
        resource_id: str,
        name: str,
        labels: Mapping[str, str],
    ) -> None:
        self.kind = kind
        self.resource_id = resource_id
        self.name = name
        self.labels = dict(labels)


class FakeDownWorld:
    """Scripted Compose-facing world shared by every fake adapter instance."""

    def __init__(self, clock: MonotonicClock) -> None:
        self.clock = clock
        self.calls: list[str] = []
        self.factory_calls = 0
        self.containers: dict[str, str] = {}
        self.networks: dict[str, str] = {}
        self.volumes: dict[str, str] = {}
        self.foreign: list[FakeResource] = []
        self.down_calls: list[dict[str, Any]] = []
        self.down_behavior = "ok"
        self.lose_volumes = False
        self.removed: list[str] = []
        self.step_seconds = 0.0

    def log(self, name: str) -> None:
        self.calls.append(name)

    def call_names(self) -> list[str]:
        return list(self.calls)

    def docker_calls(self) -> list[str]:
        return [name for name in self.calls if name in _DOCKER_CALLS]

    def factory(self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        self.factory_calls += 1
        self.log("factory")
        return FakeDownAdapter(self, manifest, identity)

    def seed_running(self, identity: Any) -> None:
        self.containers = {
            service: f"{service}-container-0001" for service in ("postgres", "redis", "grafana")
        }
        self.networks = {"default": "network-0001"}
        self.seed_volumes_only(identity)

    def seed_volumes_only(self, identity: Any) -> None:
        self.volumes = {
            "postgres-data": f"{identity.project_id}_postgres-data",
            "redis-data": f"{identity.project_id}_redis-data",
        }

    def labels(self, identity: Any, service: str | None = None) -> dict[str, str]:
        labels = {
            "com.tokenmarket.repository": TEST_REPOSITORY_LABEL,
            "com.tokenmarket.workspace-id": identity.project_id,
            "com.tokenmarket.workspace-fingerprint": identity.workspace_fingerprint,
        }
        if service is not None:
            labels["com.docker.compose.service"] = service
        return labels

    def resources(self, identity: Any) -> tuple[FakeResource, ...]:
        resources: list[FakeResource] = []
        for service, container_id in sorted(self.containers.items()):
            resources.append(
                FakeResource(
                    "container",
                    container_id,
                    f"{identity.project_id}-{service}-1",
                    self.labels(identity, service),
                )
            )
        for name, network_id in sorted(self.networks.items()):
            resources.append(
                FakeResource(
                    "network",
                    network_id,
                    f"{identity.project_id}_{name}",
                    self.labels(identity),
                )
            )
        for volume_name in sorted(self.volumes.values()):
            resources.append(
                FakeResource("volume", volume_name, volume_name, self.labels(identity))
            )
        return tuple(resources)


class FakeDownAdapter:
    """Fake down-surface adapter backed by the shared world."""

    def __init__(self, world: FakeDownWorld, manifest: Any, identity: Any) -> None:
        self._world = world
        self._manifest = manifest
        self._identity = identity

    def verify_runtime(self) -> Any:
        self._world.log("verify_runtime")
        self._world.clock.advance(self._world.step_seconds)
        return compose_module.RuntimeFacts(
            host_platform="darwin/arm64",
            container_platform="linux/arm64",
            docker_version="29.5.3",
            compose_version="5.1.4",
            daemon_arch="arm64",
        )

    def project_resources(self) -> tuple[FakeResource, ...]:
        self._world.log("project_resources")
        return self._world.resources(self._identity)

    def repository_resources(self) -> tuple[FakeResource, ...]:
        self._world.log("repository_resources")
        return tuple(self._world.foreign)

    def assert_exact_resource_ownership(self, resources: Any) -> None:
        self._world.log("assert_exact_resource_ownership")
        for resource in resources:
            if (
                resource.labels.get("com.tokenmarket.workspace-id") != self._identity.project_id
                or resource.labels.get("com.tokenmarket.workspace-fingerprint")
                != self._identity.workspace_fingerprint
            ):
                raise models_module.OwnershipConflictError(
                    "resource labels do not match the exact workspace identity; "
                    "refusing to adopt, stop, or mutate them"
                )

    def reconcile_down(self, secrets: Any, *, timeout_seconds: float) -> None:
        world = self._world
        world.log("reconcile_down")
        mapping = secrets.child_mapping()
        placeholders_ok = (
            mapping[compose_module.POSTGRES_PASSWORD_ENV]
            == compose_module.TEARDOWN_PLACEHOLDER_SECRET
            and mapping[compose_module.REDIS_CONFIG_ENV]
            == f"requirepass {compose_module.TEARDOWN_PLACEHOLDER_SECRET}\n"
            and mapping[compose_module.GRAFANA_ADMIN_PASSWORD_ENV]
            == compose_module.TEARDOWN_PLACEHOLDER_SECRET
        )
        world.down_calls.append(
            {"timeout_seconds": timeout_seconds, "placeholders": placeholders_ok}
        )
        if world.down_behavior == "partial":
            for service in ("redis", "grafana"):
                world.removed.append(world.containers.pop(service))
            raise compose_module.ComposeCommandError(
                "compose down failed; project state is retained for inspection"
            )
        if world.down_behavior != "ok":
            raise compose_module.ComposeCommandError(
                "compose down failed; project state is retained for inspection"
            )
        world.removed.extend(world.containers.values())
        world.removed.extend(world.networks.values())
        world.containers.clear()
        world.networks.clear()
        if world.lose_volumes:
            world.volumes.clear()


async def _run_down(
    *,
    clock: MonotonicClock,
    world: FakeDownWorld,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    repo_root: Path = INERT_REPO_ROOT,
    mode: str | None = None,
    mode_origin: str = "omitted",
) -> Any:
    lifecycle = _lifecycle()
    return await lifecycle.stop_local_environment(
        repo_root=repo_root,
        mode=mode,
        mode_origin=mode_origin,
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=clock,
    )


def _payloads(outcome: Any) -> list[dict[str, Any]]:
    return [event["payload"] for event in outcome.events]


def _spy_lock(
    lifecycle: Any,
    clock: MonotonicClock,
    monkeypatch: pytest.MonkeyPatch,
    world: FakeDownWorld,
) -> list[str]:
    events: list[str] = []
    real_acquire = identity_module.acquire_project_lock

    def spy(project_dir: Path, **kwargs: Any) -> Any:
        events.append("attempt")
        world.log("lock_attempt")
        lock: Any = real_acquire(project_dir, **kwargs)
        events.append("acquired")
        real_release = lock.release

        def release_spy() -> None:
            events.append("released")
            world.log("lock_released")
            real_release()

        lock.release = release_spy
        return lock

    monkeypatch.setattr(lifecycle, "acquire_project_lock", spy)
    return events


# ---------------------------------------------------------------------------
# Identity before configuration; immediate lock; contention


async def test_down_succeeds_without_reading_configuration(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    tmp_path: Path,
) -> None:
    lifecycle = _lifecycle()
    signature = inspect.signature(lifecycle.stop_local_environment)
    assert not any(
        "config" in name.lower() for name in signature.parameters
    ), "dev-down must not require, parse, or validate .env.local"
    bare_repo = tmp_path / "bare-repo"
    bare_repo.mkdir()  # no .env.local present at all
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
        repo_root=bare_repo,
    )

    assert outcome.status == "PASSED"
    assert outcome.diagnostic_code == "OK"
    assert world.containers == {} and world.networks == {}
    assert set(world.volumes) == {"postgres-data", "redis-data"}
    assert (
        world.down_calls and world.down_calls[0]["placeholders"]
    ), "down must use safe tm_local_ parse-only placeholder values"
    final = _payloads(outcome)[-1]
    assert final["phase"] == "final" and final["status"] == "PASSED"


async def test_invalid_mode_rejected_before_identity_lock_or_docker(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
        mode="test",
        mode_origin="command",
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "INVALID_MODE"
    assert world.calls == [], "mode rejection precedes identity, lock, and Docker"
    assert world.factory_calls == 0
    assert not (
        runtime_base / identity.project_id
    ).exists(), "mode rejection must not create coordination metadata"
    assert world.containers, "a rejected operation stops nothing"


async def test_lock_acquired_immediately_after_identity_before_docker(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = _lifecycle()
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    _spy_lock(lifecycle, monotonic_clock, monkeypatch, world)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    names = world.call_names()
    lock_index = names.index("lock_attempt")
    assert all(
        name in ("factory", "lock_attempt") for name in names[: lock_index + 1]
    ), f"only side-effect-free adapter creation may precede the lock: {names!r}"
    assert names.index("verify_runtime") > lock_index
    assert names.index("project_resources") > lock_index
    payloads = _payloads(outcome)
    assert payloads[0]["phase"] == "identity"
    assert "lock" in [payload["phase"] for payload in payloads]


async def test_lock_contention_rejects_with_zero_side_effects(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    project_dir = identity_module.ensure_project_runtime_dir(runtime_base, identity.project_id)
    holder = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    try:
        outcome = await _run_down(
            clock=monotonic_clock,
            world=world,
            identity=identity,
            runtime_base=runtime_base,
            manifest=manifest,
        )
    finally:
        holder.release()

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "OPERATION_IN_PROGRESS"
    assert world.docker_calls() == [], "a rejected operation touches no Docker state"
    assert "reconcile_down" not in world.call_names()
    assert world.removed == [], "a rejected operation removes nothing"
    assert set(world.containers) == {"postgres", "redis", "grafana"}
    lock_payload = next(
        payload for payload in _payloads(outcome) if payload["code"] == "OPERATION_IN_PROGRESS"
    )
    assert lock_payload["phase"] == "lock"
    assert lock_payload["status"] == "FAILED"


# ---------------------------------------------------------------------------
# Discovery, graceful stop, already-stopped idempotency, volume retention


async def test_already_stopped_volume_only_state_is_success(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_volumes_only(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert (
        "reconcile_down" not in world.call_names()
    ), "no container and no network means already stopped; nothing is reconciled"
    final = _payloads(outcome)[-1]
    assert final["status"] == "PASSED"
    assert "already stopped" in final["message"].lower()
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_orphan_network_still_requires_reconciliation(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_volumes_only(identity)
    world.networks = {"default": "orphan-network-0001"}

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert (
        "reconcile_down" in world.call_names()
    ), "an orphan network is not 'already stopped'; it must be reconciled"
    assert world.networks == {}
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_second_down_is_already_stopped_success(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    first = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )
    assert first.status == "PASSED"
    second = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert second.status == "PASSED"
    assert len(world.down_calls) == 1, "the second down reconciles nothing"
    final = _payloads(second)[-1]
    assert final["status"] == "PASSED"
    assert "already stopped" in final["message"].lower()
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_graceful_stop_is_bounded_by_the_75_second_budget(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert manifest.timeouts.stop_operation_seconds == 75
    assert len(world.down_calls) == 1
    timeout_seconds = world.down_calls[0]["timeout_seconds"]
    assert (
        0 < timeout_seconds <= 75
    ), "the subprocess/state-verification deadline is the 75-second stop budget"


async def test_named_volumes_are_retained_and_verified(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert world.containers == {} and world.networks == {}
    assert set(world.volumes.values()) == {
        f"{identity.project_id}_postgres-data",
        f"{identity.project_id}_redis-data",
    }, "ordinary down preserves every named volume"
    assert (
        world.call_names().count("project_resources") >= 2
    ), "state is verified after the stop: containers/network absent, volumes retained"


# ---------------------------------------------------------------------------
# Partial failure, retry convergence, moved-workspace reporting


async def test_partial_failure_retains_state_with_per_dependency_evidence(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    world.down_behavior = "partial"

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "STEP_FAILED"
    failed_stopping = [
        payload
        for payload in _payloads(outcome)
        if payload["phase"] == "stopping" and payload["status"] == "FAILED"
    ]
    assert {payload["dependency"] for payload in failed_stopping} == {
        "postgres"
    }, "per-dependency evidence names the dependency that failed to stop"
    assert "postgres" in world.containers, "failed state is retained for inspection"
    assert set(world.volumes) == {
        "postgres-data",
        "redis-data",
    }, "volumes are retained even when the stop fails"
    final = _payloads(outcome)[-1]
    assert final["status"] == "FAILED"
    assert "retained" in final["message"].lower()


async def test_retry_converges_after_partial_failure(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    world.down_behavior = "partial"

    first = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )
    assert first.status == "FAILED"
    world.down_behavior = "ok"

    second = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert second.status == "PASSED"
    assert world.containers == {} and world.networks == {}
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_missing_named_volume_after_down_fails_closed(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    world.lose_volumes = True

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "FAILED", "a lost named volume is failure evidence"
    assert outcome.diagnostic_code == "STEP_FAILED"
    assert "volume" in outcome.message.lower()


async def test_moved_workspace_resources_are_report_only(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_volumes_only(identity)
    world.foreign = [
        FakeResource(
            "container",
            "old-container-id",
            f"{OLD_WORKSPACE_PROJECT_ID}-postgres-1",
            {
                "com.tokenmarket.repository": "tokenmarket",
                "com.tokenmarket.workspace-id": OLD_WORKSPACE_PROJECT_ID,
                "com.tokenmarket.workspace-fingerprint": "f" * 64,
            },
        )
    ]

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert (
        "repository_resources" in world.call_names()
    ), "repository labels are scanned for moved-workspace resources"
    messages = [payload["message"] for payload in _payloads(outcome)]
    assert any(
        OLD_WORKSPACE_PROJECT_ID in message for message in messages
    ), "the old workspace project id is reported (project ids are safe to display)"
    guidance = next(message for message in messages if OLD_WORKSPACE_PROJECT_ID in message)
    assert (
        "moved" in guidance.lower() or "recover" in guidance.lower()
    ), "the finding carries recovery direction"
    assert SENTINEL_WORKSPACE_PATH not in guidance
    assert world.removed == [], "old-workspace resources are never stopped or removed"
    assert [resource.resource_id for resource in world.foreign] == ["old-container-id"]


# ---------------------------------------------------------------------------
# Safe final events and the guarded dispatch


async def test_final_events_are_safe_redacted_v2_envelopes(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert outcome.events, "the run emits v2 standard envelopes"
    assert len(outcome.plain_lines) == len(outcome.events)
    for envelope in outcome.events:
        validate_event_v2(envelope)
    assert len({envelope["correlation_id"] for envelope in outcome.events}) == 1
    stopping = [payload for payload in _payloads(outcome) if payload["phase"] == "stopping"]
    assert {payload["dependency"] for payload in stopping} == {
        "postgres",
        "redis",
        "grafana",
    }, "every dependency gets a final stopping result"
    assert all(payload["status"] == "PASSED" for payload in stopping)
    final = _payloads(outcome)[-1]
    assert final["phase"] == "final"
    assert final["status"] == "PASSED"
    assert "dependency" not in final

    blob = (
        json.dumps(list(outcome.events), ensure_ascii=False) + "\n" + "\n".join(outcome.plain_lines)
    )
    assert "tm_local_" not in blob, "placeholder or real secrets are never emitted"
    assert SENTINEL_WORKSPACE_PATH not in blob, "the workspace path is never emitted"
    assert str(runtime_base) not in blob, "the runtime directory is never emitted"
    assert "\x1b[" not in blob, "no ANSI escape sequences"
    for line in outcome.plain_lines:
        assert line.isascii() and all(
            32 <= ord(char) < 127 for char in line
        ), "plain text stays NO_COLOR-safe: no color, icons, or animation"
        assert outcome.correlation_id in line


async def test_lock_is_released_after_the_run(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    outcome = await _run_down(
        clock=monotonic_clock,
        world=world,
        identity=identity,
        runtime_base=runtime_base,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    project_dir = runtime_base / identity.project_id
    lock = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    try:
        assert lock.held, "the lock is free again after final events"
    finally:
        lock.release()


def test_guarded_dev_down_dispatch_runs_lifecycle_end_to_end(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = importlib.import_module("workflow.cli")
    if not hasattr(cli, "execute_dev_down_guarded"):
        pytest.fail("workflow.cli.execute_dev_down_guarded is not implemented yet (T049)")
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = cli.execute_dev_down_guarded(
        repo_root=INERT_REPO_ROOT,
        plain=False,
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )

    assert result == 0
    output_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    envelopes = [json.loads(line) for line in output_lines]
    assert envelopes, "the guarded dispatch must emit v2 standard envelopes"
    for envelope in envelopes:
        validate_event_v2(envelope)
    assert len({envelope["correlation_id"] for envelope in envelopes}) == 1
    assert envelopes[-1]["payload"]["phase"] == "final"
    assert envelopes[-1]["payload"]["status"] == "PASSED"
