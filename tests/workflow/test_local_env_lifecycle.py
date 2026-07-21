"""Lifecycle start orchestration tests for the SF02 local environment (T022/T032).

Covers the `make dev` ordered contract in
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 4, 8, 9 and 10 using only fake seams — no real Docker
daemon, sockets, network, or registry:

- read-only preflight ordering: effective-mode and ``.env.local`` rejection
  precede coordination metadata, the lock, and any Docker access; the read-only
  runtime/ownership/port preflight precedes lock acquisition and any mutation.
- in-lock revalidation of configuration, Compose asset, endpoint, ownership,
  and ports; drift fails before pull or mutation.
- missing-only image pull reported and timed per dependency, outside and
  before the single non-extendable 60-second readiness deadline; reconcile,
  state collection, and the three concurrent authenticated probes share that
  one deadline with no second post-wait budget.
- healthy repeat start finishes within 15 seconds without registry access or
  resource growth; partial failure retains all resources for inspection; a
  fixed rerun converges idempotently on the same resources.
- aggregate semantics: the run passes only when all three dependencies have
  fresh authenticated evidence before the deadline; one failed dependency
  fails the aggregate; a post-deadline result can never flip the run.
- lock contention rejects with ``OPERATION_IN_PROGRESS`` and zero mutation
  side effects; clean-start port conflicts name the dependency and port before
  anything is created.
- v2 standard-envelope/plain-text parity and redaction: no secrets, no URLs
  with user-info, no absolute workspace paths, no raw subprocess output, no
  color/icons/animation.
- T032: the internal guarded dev dispatch exercises the real lifecycle while
  the public ``dev``/``dev-down`` actions keep failing closed with
  ``SF02_NOT_READY`` until the v2 activation gate passes.

Every identity uses the disjoint ``tmtest-`` test prefix so fakes can never
address a developer project. These tests fail until T031 implements
``tools/workflow/local_env/lifecycle.py`` and T032 wires the guarded dispatch
in ``tools/workflow/cli.py``.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from workflow.local_env import compose as compose_module
from workflow.local_env import config as config_module
from workflow.local_env import identity as identity_module
from workflow.local_env import models as models_module

from .conftest import TEST_REPOSITORY_LABEL, MonotonicClock, assert_not_developer_project
from .helpers import find_repo_root, load_json, validate_event_v2

CONFIG_PORTS = {"postgres": 15432, "redis": 16379, "grafana": 13000}
TARGET_PORTS = {"postgres": 5432, "redis": 6379, "grafana": 3000}
SENTINEL_WORKSPACE_PATH = "/sf02-lifecycle-test-workspace"
INERT_REPO_ROOT = Path("/sf02-lifecycle-test-repo")

PROBE_KINDS = {
    models_module.DependencyId.POSTGRES: models_module.ProbeKind.POSTGRES_QUERY,
    models_module.DependencyId.REDIS: models_module.ProbeKind.REDIS_AUTH_PING,
    models_module.DependencyId.GRAFANA: models_module.ProbeKind.GRAFANA_ADMIN,
}


def _lifecycle() -> Any:
    try:
        return importlib.import_module("workflow.local_env.lifecycle")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.lifecycle is not implemented yet (T031): {exc}")


def _cli() -> Any:
    return importlib.import_module("workflow.cli")


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


@pytest.fixture
def config_bundle(synthetic_secret_factory: Any) -> dict[str, Any]:
    secrets_map = {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }
    text = (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://devuser:{secrets_map['postgres']}@"
        f"127.0.0.1:{CONFIG_PORTS['postgres']}/appdb\n"
        f"REDIS_URL=redis://default:{secrets_map['redis']}@"
        f"127.0.0.1:{CONFIG_PORTS['redis']}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{CONFIG_PORTS['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets_map['grafana']}\n"
    )
    return {
        "text": text,
        "secrets": secrets_map,
        "ports": dict(CONFIG_PORTS),
        "username": "devuser",
        "database": "appdb",
    }


def _config_text_with_ports(ports: Mapping[str, int], secrets_map: Mapping[str, str]) -> str:
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://devuser:{secrets_map['postgres']}@"
        f"127.0.0.1:{ports['postgres']}/appdb\n"
        f"REDIS_URL=redis://default:{secrets_map['redis']}@127.0.0.1:{ports['redis']}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{ports['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets_map['grafana']}\n"
    )


class ConfigReader:
    """Scripted ``.env.local`` reader recording every read on the fake clock."""

    def __init__(self, clock: MonotonicClock, *texts: str) -> None:
        if not texts:
            raise ValueError("at least one config text is required")
        self._clock = clock
        self._texts = texts
        self.call_times: list[float] = []

    def __call__(self) -> str:
        self.call_times.append(self._clock.now)
        return self._texts[min(len(self.call_times) - 1, len(self._texts) - 1)]


class FakeDockerWorld:
    """Scripted Compose-facing world shared by every fake adapter instance.

    Records an ordered call log with fake-clock timestamps; all adapter
    instances produced by :meth:`factory` (including the single-dependency
    projections the lifecycle builds for per-dependency phases) share this
    world so scripted state persists across a run.
    """

    def __init__(self, clock: MonotonicClock) -> None:
        self.clock = clock
        self.calls: list[tuple[str, float]] = []
        self.factory_calls = 0
        self.images: set[str] = set()
        self.pull_seconds: dict[str, float] = {}
        self.pull_failures: set[str] = set()
        self.containers: dict[str, dict[str, Any]] = {}
        self.occupied_ports: set[int] = set()
        self.reconcile_calls: list[dict[str, Any]] = []
        self.reconcile_failure: str | None = None
        self.up_seconds = 0.0
        self.step_seconds = 0.0

    def log(self, name: str) -> None:
        self.calls.append((name, self.clock.now))

    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def call_time(self, name: str, occurrence: int = 0) -> float:
        matches = [time for n, time in self.calls if n == name]
        if len(matches) <= occurrence:
            raise AssertionError(f"world call {name!r} occurrence {occurrence} is missing")
        return matches[occurrence]

    def factory(self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        self.factory_calls += 1
        self.log("factory")
        return FakeComposeAdapter(self, manifest, identity)

    def seed_images(self) -> None:
        self.images.update(CONFIG_PORTS)

    def seed_running(self, ports: Mapping[str, int]) -> None:
        for service, port in ports.items():
            self.containers[service] = {
                "id": f"{service}-container-0001",
                "published_port": port,
                "target_port": TARGET_PORTS[service],
            }

    def container_ids(self) -> dict[str, str]:
        return {service: record["id"] for service, record in self.containers.items()}

    def service_states(self, identity: Any) -> tuple[Any, ...]:
        return tuple(
            _service_state(identity, service, record)
            for service, record in sorted(self.containers.items())
        )

    def start_containers(self, derived_env: Mapping[str, str]) -> None:
        ports = {
            "postgres": int(derived_env[compose_module.POSTGRES_HOST_PORT_ENV]),
            "redis": int(derived_env[compose_module.REDIS_HOST_PORT_ENV]),
            "grafana": int(derived_env[compose_module.GRAFANA_HOST_PORT_ENV]),
        }
        for service, port in ports.items():
            # Idempotent reconcile: an existing owned instance keeps its identity.
            if service not in self.containers:
                self.containers[service] = {
                    "id": f"{service}-container-0001",
                    "published_port": port,
                    "target_port": TARGET_PORTS[service],
                }


def _service_state(identity: Any, service: str, record: Mapping[str, Any]) -> Any:
    labels = {
        compose_module.LABEL_REPOSITORY: TEST_REPOSITORY_LABEL,
        compose_module.LABEL_WORKSPACE_ID: identity.project_id,
        compose_module.LABEL_WORKSPACE_FINGERPRINT: identity.workspace_fingerprint,
    }
    publishers: tuple[Any, ...] = ()
    if record.get("published_port") is not None:
        publishers = (
            compose_module.PublisherInfo(
                host_ip="127.0.0.1",
                target_port=record["target_port"],
                published_port=record["published_port"],
                protocol="tcp",
            ),
        )
    return compose_module.ServiceState(
        project=identity.project_id,
        service=service,
        state="running",
        health="healthy",
        labels=labels,
        publishers=publishers,
    )


class FakeComposeAdapter:
    """Fake ComposeAdapter protocol implementation backed by a shared world."""

    def __init__(self, world: FakeDockerWorld, manifest: Any, identity: Any) -> None:
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

    def verified_compose_bytes(self) -> bytes:
        self._world.log("verified_compose_bytes")
        return b"# verified committed compose bytes\n"

    def project_state(self) -> tuple[Any, ...]:
        self._world.log("project_state")
        self._world.clock.advance(self._world.step_seconds)
        return self._world.service_states(self._identity)

    def assert_exact_ownership(self, state: Any) -> None:
        self._world.log("assert_exact_ownership")

    def assert_no_workspace_path_in_labels(self, state: Any) -> None:
        self._world.log("assert_no_workspace_path_in_labels")

    def assert_loopback_publishers(self, state: Any) -> None:
        self._world.log("assert_loopback_publishers")

    def preflight_ports(self, state: Any, desired_ports: Mapping[Any, int]) -> None:
        world = self._world
        for definition in self._manifest.dependencies:
            port = desired_ports[definition.id]
            world.log(f"preflight_ports:{definition.id.value}")
            if port in world.occupied_ports:
                raise compose_module.PortConflictError(
                    f"{definition.id.value} desired loopback port {port} is "
                    "unavailable; free the port or change its URL and retry"
                )

    def ensure_images(self, runtime: Any) -> tuple[Any, ...]:
        world = self._world
        records = []
        for definition in self._manifest.dependencies:
            dep = definition.id.value
            world.log(f"inspect:{dep}")
            pulled = False
            if dep not in world.images:
                world.log(f"pull:{dep}")
                if dep in world.pull_failures:
                    raise compose_module.ImageUnavailableError(
                        f"{dep} image pull failed; check registry access and disk space"
                    )
                world.clock.advance(world.pull_seconds.get(dep, 0.0))
                world.images.add(dep)
                pulled = True
            world.log(f"verify:{dep}")
            records.append(compose_module.ImagePullRecord(dependency=definition.id, pulled=pulled))
        return tuple(records)

    def reconcile_up(
        self,
        secrets: Any,
        *,
        timeout_seconds: float,
        derived_env: Mapping[str, str] | None = None,
    ) -> None:
        world = self._world
        world.log("reconcile_up")
        derived = dict(derived_env or {})
        world.reconcile_calls.append({"timeout_seconds": timeout_seconds, "derived_env": derived})
        if world.reconcile_failure == "compose":
            raise compose_module.ComposeCommandError(
                "compose reconcile failed; project state is retained for inspection"
            )
        if world.reconcile_failure == "port-race":
            world.occupied_ports.add(int(derived[compose_module.GRAFANA_HOST_PORT_ENV]))
            raise compose_module.PortConflictError(
                "a desired loopback port became unavailable during reconcile; "
                "free the port or change its URL and retry"
            )
        world.clock.advance(world.up_seconds)
        world.start_containers(derived)


class FakeProbePlan:
    """Scripted concurrent probe stand-ins on the shared monotonic clock."""

    def __init__(self, clock: MonotonicClock) -> None:
        self.clock = clock
        self.results: dict[str, str] = {
            "postgres": "ready",
            "redis": "ready",
            "grafana": "ready",
        }
        self.reasons: dict[str, str] = {}
        self.seconds: dict[str, float] = {
            "postgres": 0.2,
            "redis": 0.2,
            "grafana": 0.2,
        }
        self.calls: list[tuple[str, str, float, float, int]] = []

    def fn(self) -> Any:
        async def probe(target: Any, deadline: float) -> Any:
            dep = target.dependency.value
            self.calls.append((dep, "start", deadline, self.clock.now, target.port))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.clock.advance(self.seconds[dep])
            self.calls.append((dep, "end", deadline, self.clock.now, target.port))
            ready = self.results[dep] == "ready"
            reason = ""
            if not ready:
                reason = self.reasons.get(
                    dep, f"{dep} rejected the configured credentials; fix the URL and retry"
                )
            return models_module.DependencyHealthResult(
                dependency=target.dependency,
                liveness=(
                    models_module.LivenessState.ALIVE
                    if ready
                    else models_module.LivenessState.NOT_ALIVE
                ),
                readiness=(
                    models_module.ReadinessState.READY
                    if ready
                    else models_module.ReadinessState.NOT_READY
                ),
                probe=PROBE_KINDS[target.dependency],
                checked_at=datetime.now(timezone.utc),
                duration_ms=int(self.seconds[dep] * 1000),
                code="OK" if ready else "DEPENDENCY_NOT_READY",
                safe_reason=reason,
            )

        return probe

    def entries(self, kind: str) -> list[tuple[str, str, float, float, int]]:
        return [call for call in self.calls if call[1] == kind]


def _clock_sleep(clock: MonotonicClock) -> Any:
    async def _sleep(seconds: float) -> None:
        clock.advance(seconds)

    return _sleep


async def _run_start(
    *,
    clock: MonotonicClock,
    world: FakeDockerWorld,
    config_reader: Callable[[], str],
    identity: Any,
    runtime_base: Path,
    probe_plan: FakeProbePlan,
    manifest: Any,
    mode: str | None = None,
    mode_origin: str = "omitted",
) -> Any:
    lifecycle = _lifecycle()
    return await lifecycle.start_local_environment(
        repo_root=INERT_REPO_ROOT,
        mode=mode,
        mode_origin=mode_origin,
        identity=identity,
        config_reader=config_reader,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        probe_fn=probe_plan.fn(),
        clock=clock,
        sleep=_clock_sleep(clock),
    )


def _payloads(outcome: Any) -> list[dict[str, Any]]:
    return [event["payload"] for event in outcome.events]


def _phases(outcome: Any) -> list[str]:
    return [payload["phase"] for payload in _payloads(outcome)]


def _spy_lock(
    lifecycle: Any,
    clock: MonotonicClock,
    monkeypatch: pytest.MonkeyPatch,
    world: FakeDockerWorld | None = None,
) -> list:
    events: list[tuple[str, float]] = []
    real_acquire = identity_module.acquire_project_lock

    def spy(project_dir: Path, **kwargs: Any) -> Any:
        events.append(("attempt", clock.now))
        if world is not None:
            world.log("lock_attempt")
        lock = real_acquire(project_dir, **kwargs)
        events.append(("acquired", clock.now))
        real_release = lock.release

        def release_spy() -> None:
            events.append(("released", clock.now))
            if world is not None:
                world.log("lock_released")
            real_release()

        lock.release = release_spy
        return lock

    monkeypatch.setattr(lifecycle, "acquire_project_lock", spy)
    return events


# ---------------------------------------------------------------------------
# Preflight ordering: mode/config rejection precedes coordination and Docker


async def test_invalid_mode_rejected_before_config_lock_or_docker(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        mode="test",
        mode_origin="command",
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "INVALID_MODE"
    assert reader.call_times == [], "mode rejection must precede reading .env.local"
    assert world.factory_calls == 0, "mode rejection must precede any Docker access"
    assert world.calls == []
    assert plan.calls == []
    assert not (
        runtime_base / identity.project_id
    ).exists(), "mode rejection must not create coordination metadata"
    payloads = _payloads(outcome)
    assert payloads[0]["status"] == "FAILED"
    assert payloads[0]["code"] == "INVALID_MODE"
    assert payloads[-1]["phase"] == "final"
    assert payloads[-1]["status"] == "FAILED"


async def test_environment_origin_mode_rejected_before_config_or_docker(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        mode="local",
        mode_origin="environment",
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "INVALID_MODE"
    assert reader.call_times == []
    assert world.factory_calls == 0
    assert not (runtime_base / identity.project_id).exists()


async def test_missing_config_rejected_before_lock_or_docker(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)

    def missing_reader() -> str:
        raise FileNotFoundError(".env.local")

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=missing_reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "INVALID_CONFIG"
    assert world.factory_calls == 0, "config rejection must precede any Docker access"
    assert plan.calls == []
    assert not (runtime_base / identity.project_id).exists()


@pytest.mark.parametrize(
    ("text", "expected_code"),
    (
        (
            "MODE=test\n"
            "DATABASE_URL=postgresql://devuser:tm_local_" + "a" * 40 + "@127.0.0.1:15432/appdb\n",
            "INVALID_MODE",
        ),
        (
            "MODE=local\n"
            "DATABASE_URL=postgresql://devuser:tm_local_" + "a" * 40 + "@10.0.0.8:15432/appdb\n"
            "REDIS_URL=redis://default:tm_local_" + "b" * 40 + "@127.0.0.1:16379/0\n"
            "GRAFANA_URL=http://127.0.0.1:13000\n"
            "GRAFANA_ADMIN_PASSWORD=tm_local_" + "c" * 40 + "\n",
            "INVALID_CONFIG",
        ),
    ),
    ids=["file-mode-not-local", "non-loopback-url"],
)
async def test_invalid_config_rejected_before_lock_or_docker(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    text: str,
    expected_code: str,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, text)

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == expected_code
    assert world.factory_calls == 0, "config rejection must precede any Docker access"
    assert plan.calls == []
    assert not (
        runtime_base / identity.project_id
    ).exists(), "config rejection must not create even coordination metadata"


async def test_command_line_local_mode_is_accepted(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    world.seed_running(config_bundle["ports"])
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        mode="local",
        mode_origin="command line",
    )

    assert outcome.status == "PASSED"


# ---------------------------------------------------------------------------
# Read-only preflight ordering and in-lock revalidation


async def test_readonly_preflight_precedes_lock_and_mutation(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = _lifecycle()
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])
    lock_events = _spy_lock(lifecycle, monotonic_clock, monkeypatch, world)

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    names = world.call_names()
    lock_index = names.index("lock_attempt")
    read_only = {
        "factory",
        "verify_runtime",
        "project_state",
        "assert_exact_ownership",
        "assert_no_workspace_path_in_labels",
        "assert_loopback_publishers",
    }
    mutation_prefixes = ("inspect:", "pull:", "verify:", "reconcile_up")

    pre_lock = names[:lock_index]
    assert pre_lock, "read-only preflight must happen before the lock"
    for name in pre_lock:
        assert name in read_only or name.startswith(
            "preflight_ports:"
        ), f"unexpected pre-lock call {name!r}"
    assert (
        reader.call_times[0] <= world.calls[0][1]
    ), "configuration must be validated before any Docker access"
    assert "verify_runtime" in pre_lock
    assert "project_state" in pre_lock
    assert "preflight_ports:grafana" in pre_lock

    post_lock = [name for index, name in enumerate(names) if index > lock_index]
    assert "verify_runtime" in post_lock, "endpoint must be revalidated inside the lock"
    assert "project_state" in post_lock, "ownership/state must be revalidated in the lock"
    assert "preflight_ports:grafana" in post_lock, "ports must be revalidated in the lock"
    first_mutation = next(
        index for index, name in enumerate(names) if name.startswith(mutation_prefixes)
    )
    assert first_mutation > lock_index, "no mutation before the project lock"
    assert "reconcile_up" in post_lock
    assert names.index("lock_released") == len(names) - 1
    assert (
        dict(lock_events)["released"] >= plan.entries("end")[-1][3]
    ), "the lock must stay held across readiness and final event emission"


async def test_in_lock_revalidation_rechecks_config_asset_endpoint_ownership_ports(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    names = world.call_names()
    assert len(reader.call_times) == 2, "configuration must be re-read inside the lock"
    assert names.count("verify_runtime") == 2, "endpoint revalidation must rerun in lock"
    assert names.count("project_state") == 3, "pre-lock, in-lock, and post-reconcile state"
    assert names.count("preflight_ports:postgres") == 2
    assert names.count("preflight_ports:redis") == 2
    assert names.count("preflight_ports:grafana") == 2
    assert "verified_compose_bytes" in names, "Compose asset must be revalidated in lock"
    assert names.index("verified_compose_bytes") > names.index("preflight_ports:grafana")
    assert names.index("inspect:postgres") > names.index(
        "verify_runtime", names.index("verify_runtime") + 1
    )


async def test_in_lock_config_drift_to_invalid_fails_before_pull_or_mutation(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = _lifecycle()
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    invalid_second_read = "MODE=local\nDATABASE_URL=postgresql://127.0.0.1:15432\n"
    reader = ConfigReader(monotonic_clock, config_bundle["text"], invalid_second_read)
    lock_events = _spy_lock(lifecycle, monotonic_clock, monkeypatch)

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "INVALID_CONFIG"
    assert len(reader.call_times) == 2
    names = world.call_names()
    assert not any(name.startswith("inspect:") for name in names), "drift fails before pull"
    assert "reconcile_up" not in names
    assert plan.calls == []
    assert [name for name, _ in lock_events].count(
        "released"
    ) == 1, "the lock must be released even when revalidation fails"


async def test_in_lock_config_port_drift_uses_fresh_facts(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    drifted_ports = {"postgres": 25432, "redis": 26379, "grafana": 23000}
    second_read = _config_text_with_ports(drifted_ports, config_bundle["secrets"])
    reader = ConfigReader(monotonic_clock, config_bundle["text"], second_read)

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    derived = world.reconcile_calls[0]["derived_env"]
    assert derived[compose_module.POSTGRES_HOST_PORT_ENV] == "25432"
    assert derived[compose_module.REDIS_HOST_PORT_ENV] == "26379"
    assert derived[compose_module.GRAFANA_HOST_PORT_ENV] == "23000"
    probe_ports = {call[0]: call[4] for call in plan.entries("start")}
    assert probe_ports == drifted_ports, "probes must target the in-lock configuration"


# ---------------------------------------------------------------------------
# Image pull timing vs the single readiness deadline


async def test_missing_images_pulled_before_deadline_with_per_dependency_timing(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.pull_seconds = {"postgres": 3.0, "redis": 4.0, "grafana": 5.0}
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    pull_events = [p for p in _payloads(outcome) if p["phase"] == "image-pull"]
    assert [p["dependency"] for p in pull_events] == ["postgres", "redis", "grafana"]
    assert [p["duration_ms"] for p in pull_events] == [
        3000,
        4000,
        5000,
    ], "each dependency pull is timed separately"
    assert all(p["status"] == "PASSED" for p in pull_events)
    assert all("pulled" in p["message"] for p in pull_events)
    verify_events = [p for p in _payloads(outcome) if p["phase"] == "image-verify"]
    assert [p["dependency"] for p in verify_events] == ["postgres", "redis", "grafana"]

    deadline = plan.entries("start")[0][2]
    last_verify = world.call_time("verify:grafana")
    assert deadline == pytest.approx(
        last_verify + 60.0
    ), "the 60-second readiness deadline starts only after image verification"
    assert world.call_time("pull:grafana") < deadline - 60.0 + 5.0
    assert (
        world.call_time("pull:postgres") < last_verify
    ), "pull completes before the readiness deadline begins"


async def test_readiness_deadline_is_single_sixty_second_and_non_extendable(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    world.up_seconds = 7.0
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert len(world.reconcile_calls) == 1
    assert world.reconcile_calls[0]["timeout_seconds"] == pytest.approx(
        60.0
    ), "reconcile consumes the same 60-second deadline"
    deadlines = {call[2] for call in plan.calls}
    assert len(deadlines) == 1, "every probe shares exactly one deadline"
    deadline = deadlines.pop()
    assert deadline == pytest.approx(world.call_time("verify:grafana") + 60.0)
    assert len(plan.entries("end")) == 3, "no probe re-invocation beyond the deadline"


async def test_probes_run_concurrently_under_one_shared_deadline(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    starts = [i for i, call in enumerate(plan.calls) if call[1] == "start"]
    ends = [i for i, call in enumerate(plan.calls) if call[1] == "end"]
    assert len(starts) == 3 and len(ends) == 3
    assert max(starts) < min(
        ends
    ), "all three probes must be scheduled before any completes (concurrent)"
    assert [call[0] for call in plan.entries("start")] == ["postgres", "redis", "grafana"]


# ---------------------------------------------------------------------------
# Healthy fast path, partial failure, retry convergence


async def test_healthy_repeat_start_fast_without_pulls_or_resource_growth(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    world.seed_running(config_bundle["ports"])
    plan = FakeProbePlan(monotonic_clock)
    plan.seconds = {"postgres": 0.1, "redis": 0.1, "grafana": 0.1}
    reader = ConfigReader(monotonic_clock, config_bundle["text"])
    ids_before = world.container_ids()

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    assert outcome.duration_ms <= 15_000, "healthy repeat must finish within 15 seconds"
    names = world.call_names()
    assert not any(
        name.startswith("pull:") for name in names
    ), "a healthy repeat must not contact the registry"
    assert names.count("reconcile_up") == 1
    assert world.container_ids() == ids_before, "no container identity may change"
    assert len(world.containers) == 3, "no container, network, or volume growth"


async def test_partial_readiness_failure_retains_resources_and_fails_aggregate(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    plan.results["redis"] = "auth-failed"
    plan.reasons["redis"] = "redis rejected the configured password; fix REDIS_URL and retry"
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "DEPENDENCY_NOT_READY"
    readiness = {p["dependency"]: p for p in _payloads(outcome) if p["phase"] == "readiness"}
    assert readiness["postgres"]["status"] == "PASSED"
    assert readiness["grafana"]["status"] == "PASSED"
    assert readiness["redis"]["status"] == "FAILED"
    assert readiness["redis"]["code"] == "DEPENDENCY_NOT_READY"
    assert readiness["redis"]["message"] == plan.reasons["redis"]
    final = _payloads(outcome)[-1]
    assert final["phase"] == "final" and final["status"] == "FAILED"
    assert len(outcome.dependency_results) == 3
    assert len(world.containers) == 3, "partial failure retains every resource"
    forbidden = {"down", "stop", "rm", "remove", "prune", "volume"}
    assert not any(
        any(marker in name for marker in forbidden) for name in world.call_names()
    ), "failure must never down, stop, remove, or prune retained resources"


async def test_retry_after_failure_converges_on_the_same_resources(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    plan.results["grafana"] = "unexpected-response"
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    first = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )
    assert first.status == "FAILED"
    assert first.diagnostic_code == "DEPENDENCY_NOT_READY"
    ids_after_failure = world.container_ids()
    assert len(ids_after_failure) == 3, "failed run retains inspectable state"
    boundary = len(world.calls)

    plan.results["grafana"] = "ready"
    second = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert second.status == "PASSED"
    rerun_names = world.call_names()[boundary:]
    assert not any(
        name.startswith("pull:") for name in rerun_names
    ), "retry reuses already-pulled images (no registry access)"
    assert "reconcile_up" in rerun_names, "retry reconciles again idempotently"
    assert world.container_ids() == ids_after_failure, "retry converges on the same owned resources"
    assert len(world.reconcile_calls) == 2


# ---------------------------------------------------------------------------
# Deadline edges


async def test_probe_completion_exactly_at_deadline_passes(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    plan = FakeProbePlan(monotonic_clock)
    plan.seconds = {"postgres": 20.0, "redis": 20.0, "grafana": 20.0}
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED", "evidence exactly at the deadline is still fresh"
    readiness = [p for p in _payloads(outcome) if p["phase"] == "readiness"]
    assert all(p["status"] == "PASSED" for p in readiness)


async def test_probe_completion_after_deadline_fails_without_second_budget(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    plan = FakeProbePlan(monotonic_clock)
    plan.seconds = {"postgres": 20.0, "redis": 20.0, "grafana": 20.5}
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "DEPENDENCY_NOT_READY"
    readiness = {p["dependency"]: p for p in _payloads(outcome) if p["phase"] == "readiness"}
    assert readiness["postgres"]["status"] == "PASSED", "fresh in-deadline evidence stands"
    assert readiness["redis"]["status"] == "PASSED"
    assert readiness["grafana"]["status"] == "FAILED"
    assert readiness["grafana"]["code"] == "DEPENDENCY_NOT_READY"
    assert "deadline" in readiness["grafana"]["message"]
    assert len(plan.entries("end")) == 3, "no post-deadline probe budget may exist"
    assert len(world.containers) == 3, "timeout retains resources for inspection"


async def test_deadline_exhausted_by_reconcile_skips_probes_and_retains(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    world.up_seconds = 61.0
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "DEPENDENCY_NOT_READY"
    assert world.reconcile_calls[0]["timeout_seconds"] == pytest.approx(60.0)
    assert plan.calls == [], "no probe may run once the shared deadline is exhausted"
    readiness = [p for p in _payloads(outcome) if p["phase"] == "readiness"]
    assert len(readiness) == 3
    assert all(p["status"] == "FAILED" for p in readiness)
    assert all(p["code"] == "DEPENDENCY_NOT_READY" for p in readiness)
    assert len(world.containers) == 3, "resources stay retained after the timeout"


# ---------------------------------------------------------------------------
# Lock contention, port conflicts, image failures


async def test_lock_contention_rejects_with_zero_side_effects(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    project_dir = identity_module.ensure_project_runtime_dir(runtime_base, identity.project_id)
    holder = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    try:
        outcome = await _run_start(
            clock=monotonic_clock,
            world=world,
            config_reader=reader,
            identity=identity,
            runtime_base=runtime_base,
            probe_plan=plan,
            manifest=manifest,
        )
    finally:
        holder.release()

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "OPERATION_IN_PROGRESS"
    names = world.call_names()
    assert not any(name.startswith(("inspect:", "pull:", "verify:")) for name in names)
    assert "reconcile_up" not in names
    assert plan.calls == [], "a rejected operation probes nothing"
    assert world.containers == {}, "a rejected operation creates nothing"
    assert world.images == set(), "a rejected operation pulls nothing"
    lock_payload = next(p for p in _payloads(outcome) if p["code"] == "OPERATION_IN_PROGRESS")
    assert lock_payload["phase"] == "lock"
    assert lock_payload["status"] == "FAILED"


async def test_port_conflict_names_dependency_before_any_creation(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.occupied_ports.add(CONFIG_PORTS["grafana"])
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "PORT_CONFLICT"
    conflict = next(p for p in _payloads(outcome) if p["code"] == "PORT_CONFLICT")
    assert conflict["status"] == "FAILED"
    assert conflict["dependency"] == "grafana"
    assert "grafana" in conflict["message"] and "13000" in conflict["message"]
    names = world.call_names()
    assert not any(
        name.startswith(("inspect:", "pull:")) for name in names
    ), "port conflict fails before any image or resource work"
    assert "reconcile_up" not in names
    assert plan.calls == []
    assert world.containers == {}, "clean-start conflict creates no partial resources"


async def test_reconcile_port_race_is_attributed_and_retained(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.reconcile_failure = "port-race"
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "PORT_CONFLICT"
    conflict = next(p for p in _payloads(outcome) if p["code"] == "PORT_CONFLICT")
    assert conflict["phase"] == "reconcile"
    assert conflict["dependency"] == "grafana"
    assert plan.calls == []
    assert world.containers == {}, "the lost race creates no partial containers"


async def test_image_unavailable_fails_before_reconcile_and_readiness(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    world.pull_failures.add("redis")
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "IMAGE_UNAVAILABLE"
    pull_events = [p for p in _payloads(outcome) if p["phase"] == "image-pull"]
    assert [(p["dependency"], p["status"]) for p in pull_events] == [
        ("postgres", "PASSED"),
        ("redis", "FAILED"),
    ], "the failing dependency is named and later dependencies are not attempted"
    failed = pull_events[1]
    assert failed["code"] == "IMAGE_UNAVAILABLE"
    names = world.call_names()
    assert "reconcile_up" not in names, "image failure precedes any reconcile"
    assert plan.calls == [], "the readiness deadline never starts on image failure"
    assert world.containers == {}


# ---------------------------------------------------------------------------
# Event/plain-text parity and redaction


async def test_events_match_plain_text_and_never_leak_unsafe_values(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    outcome = await _run_start(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
    )

    assert outcome.status == "PASSED"
    events = outcome.events
    lines = outcome.plain_lines
    assert len(events) == len(lines) and events, "every envelope has one plain-text line"
    for envelope in events:
        validate_event_v2(envelope)

    event_ids = [envelope["event_id"] for envelope in events]
    assert len(set(event_ids)) == len(event_ids), "event ids must be unique"
    correlation_ids = {envelope["correlation_id"] for envelope in events}
    assert len(correlation_ids) == 1, "one lifecycle-run correlation id"
    correlation_id = correlation_ids.pop()
    assert outcome.correlation_id == correlation_id

    for envelope, line in zip(events, lines):
        payload = envelope["payload"]
        assert f"[{payload['status']}]" in line
        assert f"[{payload['code']}]" in line
        assert payload["message"] in line
        assert correlation_id in line
        if "dependency" in payload:
            assert f"/{payload['phase']} {payload['dependency']}:" in line
        else:
            assert f"/{payload['phase']}:" in line
        assert line.isascii() and all(
            32 <= ord(char) < 127 for char in line
        ), "plain text stays NO_COLOR-safe: no color, icons, or animation"

    blob = json.dumps(events, ensure_ascii=False) + "\n" + "\n".join(lines)
    for secret in config_bundle["secrets"].values():
        assert secret not in blob
    assert "tm_local_" not in blob, "synthetic secret grammar never survives emission"
    assert config_bundle["username"] not in blob, "URL user-info is never displayed"
    assert "@" not in blob, "no URL with user-info may appear"
    assert SENTINEL_WORKSPACE_PATH not in blob, "the workspace path is never emitted"
    assert str(runtime_base) not in blob, "the runtime directory is never emitted"
    assert "\x1b[" not in blob, "no ANSI escape sequences"

    final = _payloads(outcome)[-1]
    assert final["phase"] == "final" and final["status"] == "PASSED"
    assert "127.0.0.1:15432/appdb" in final["message"]
    assert "127.0.0.1:16379/0" in final["message"]
    assert "127.0.0.1:13000" in final["message"]


# ---------------------------------------------------------------------------
# T032: guarded dev dispatch vs the public fail-closed gate


def test_public_execute_action_stays_sf02_not_ready(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _cli()
    monkeypatch.delenv("NO_COLOR", raising=False)
    for action in ("dev", "dev-down"):
        result = cli.execute_action(action, repo_root=find_repo_root(), plain=True)
        output = capsys.readouterr().out
        assert result == 1, f"public {action} must keep failing closed until T074"
        assert "SF02_NOT_READY" in output


def _run_guarded(
    *,
    clock: MonotonicClock,
    world: FakeDockerWorld,
    config_reader: Callable[[], str],
    identity: Any,
    runtime_base: Path,
    probe_plan: FakeProbePlan,
    manifest: Any,
    plain: bool,
    mode: str | None = None,
    mode_origin: str = "omitted",
) -> int:
    cli = _cli()
    return cli.execute_dev_guarded(
        repo_root=INERT_REPO_ROOT,
        mode=mode,
        mode_origin=mode_origin,
        plain=plain,
        identity=identity,
        config_reader=config_reader,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        probe_fn=probe_plan.fn(),
        clock=clock,
        sleep=_clock_sleep(clock),
    )


def test_guarded_dev_dispatch_runs_lifecycle_end_to_end(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = _run_guarded(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        plain=False,
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


def test_guarded_dev_dispatch_plain_text_output(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    result = _run_guarded(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        plain=True,
    )

    assert result == 0
    output_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert output_lines
    for line in output_lines:
        assert not line.startswith("{"), "plain mode must not emit JSONL"
        assert "correlation_id=" in line
        assert line.startswith("[")
    assert output_lines[-1].startswith("[PASSED]")


def test_guarded_dev_dispatch_failure_returns_non_zero(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    plan.results["redis"] = "auth-failed"
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    result = _run_guarded(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        plain=True,
    )

    assert result == 1
    output = capsys.readouterr().out
    assert "DEPENDENCY_NOT_READY" in output
    assert "[FAILED]" in output


def test_guarded_dev_dispatch_rejects_non_local_mode_fail_closed(
    monotonic_clock: MonotonicClock,
    config_bundle: dict[str, Any],
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = FakeDockerWorld(monotonic_clock)
    plan = FakeProbePlan(monotonic_clock)
    reader = ConfigReader(monotonic_clock, config_bundle["text"])

    result = _run_guarded(
        clock=monotonic_clock,
        world=world,
        config_reader=reader,
        identity=identity,
        runtime_base=runtime_base,
        probe_plan=plan,
        manifest=manifest,
        plain=True,
        mode="prod",
        mode_origin="command",
    )

    assert result == 1
    output = capsys.readouterr().out
    assert "INVALID_MODE" in output
    assert world.factory_calls == 0, "mode rejection precedes any Docker access"
    assert reader.call_times == []
