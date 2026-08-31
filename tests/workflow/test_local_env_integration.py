"""Real-Compose integration tests for the SF02 local environment (T025).

These tests run the guarded ``make dev`` lifecycle against the REAL local
Docker daemon with disposable, exact test-labeled projects (``tmtest-*``),
dynamic loopback ports, and synthetic credentials (fixtures from
``tests/workflow/conftest.py``, T035). They never address developer
``tokenmarket-*`` resources; the fixture finalizer tears every project down
by exact labels even on failure and proves zero tmtest leftovers.

Missing-image cases use a test-scoped ComposeAdapter ``run`` seam to simulate
a local redis ``image inspect`` miss without deleting or retagging daemon
images (required on Docker Desktop containerd, where digest-only RepoTags
cannot be untagged). Other suite tests still exercise the real daemon.
Tests in this file run sequentially (module order) to avoid port and lock
interference between projects.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from typing import Any, Mapping, Sequence

# Locked asyncpg ships no py.typed marker (same reviewed exception as probes.py).
import asyncpg  # type: ignore[import-untyped]
import pytest

from workflow.local_env.compose import default_bind_check, default_run
from workflow.local_env.lifecycle import LifecycleRunOutcome
from workflow.local_env.models import (
    DependencyHealthResult,
    DependencyId,
    LivenessState,
    ReadinessState,
)
from workflow.local_env.probes import ProbeTarget, probe_dependency

from .conftest import (
    NetworkProbeRunner,
    RealComposeProject,
    RealComposeProjectFactory,
    readiness_window_seconds,
)
from .helpers import read_events_v2_jsonl

DOCKER_SHORT_TIMEOUT = 30.0
PROBE_DEADLINE_SECONDS = 15.0


def _docker(
    args: Sequence[str], *, timeout: float = DOCKER_SHORT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Bounded docker CLI call for test bookkeeping; fails the test on error."""
    result = subprocess.run(
        ["docker", *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:200]
        raise AssertionError(
            f"docker {args[0]!r} failed with exit {result.returncode} "
            f"during test bookkeeping: {detail}"
        )
    return result


def _container_ids_by_service(project: RealComposeProject) -> dict[str, str]:
    listed = _docker(
        [
            "ps",
            "-aq",
            "--no-trunc",
            "--filter",
            f"label=com.tokenmarket.workspace-id={project.project_id}",
        ]
    )
    ids = listed.stdout.split()
    mapping: dict[str, str] = {}
    if not ids:
        return mapping
    documents: Any = json.loads(_docker(["inspect", *ids]).stdout)
    for entry in documents:
        service = entry["Config"]["Labels"].get("com.docker.compose.service")
        if isinstance(service, str):
            mapping[service] = str(entry["Id"])
    return mapping


def _serialized_outcome(outcome: LifecycleRunOutcome) -> str:
    return json.dumps(outcome.events) + "\n" + "\n".join(outcome.plain_lines) + outcome.message


def _wait_port_free(port: int, *, timeout: float = 60.0) -> None:
    """Wait until a removed container's host port is released.

    Docker Desktop's host-side port forwarder lingers well after the
    container is gone (measured ~25 s on this host after stop+rm); the wait
    is test-harness hygiene around that host lag, never a relaxation of the
    lifecycle's own port contract.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            time.sleep(0.2)
            continue
        finally:
            probe.close()
        return
    raise AssertionError(f"host port {port} was still bound after {timeout}s")


def _redis_image_ref(factory: RealComposeProjectFactory) -> str:
    return factory.manifest().dependency(DependencyId.REDIS).image_ref


def _assert_redis_image_ref_present(factory: RealComposeProjectFactory) -> str:
    """Prove redis ``image_ref`` is locally inspectable with digest identity."""
    redis_ref = _redis_image_ref(factory)
    document = json.loads(_docker(["image", "inspect", redis_ref]).stdout)[0]
    assert document.get("Os") == "linux", "redis image must be a linux variant"
    assert document.get("Architecture") in {
        "amd64",
        "arm64",
    }, "redis image must report a native architecture"
    repo_digests = document.get("RepoDigests")
    assert (
        isinstance(repo_digests, list) and repo_digests
    ), "redis image must expose RepoDigests for digest identity verification"
    return redis_ref


def _is_docker_image_inspect(argv: Sequence[str], image_ref: str) -> bool:
    return (
        len(argv) >= 4
        and argv[0] == "docker"
        and argv[1] == "image"
        and argv[2] == "inspect"
        and image_ref in argv
    )


def _is_docker_pull(argv: Sequence[str], image_ref: str) -> bool:
    return len(argv) >= 3 and argv[0] == "docker" and argv[1] == "pull" and image_ref in argv


def _no_such_image_result(argv: list[str], image_ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=argv,
        returncode=1,
        stdout="",
        stderr=f"Error: No such image: {image_ref}\n",
    )


class _RedisInspectMissUntilPullRun:
    """Test-scoped ``run`` seam for the success missing-image path.

    State: hide redis inspect → real redis pull (rc==0 unhides) → real inspect.
    """

    def __init__(self, redis_image_ref: str) -> None:
        self._redis_image_ref = redis_image_ref
        self._hide_inspect = True
        self.pull_succeeded = False

    def __call__(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = [str(arg) for arg in args]
        if _is_docker_image_inspect(argv, self._redis_image_ref) and self._hide_inspect:
            return _no_such_image_result(argv, self._redis_image_ref)
        if _is_docker_pull(argv, self._redis_image_ref):
            result = default_run(argv, **kwargs)
            if result.returncode == 0:
                self._hide_inspect = False
                self.pull_succeeded = True
            return result
        return default_run(argv, **kwargs)


class _RedisInspectMissTimeoutPullRun:
    """Test-scoped ``run`` seam: redis inspect miss + deterministic pull timeout."""

    def __init__(self, redis_image_ref: str) -> None:
        self._redis_image_ref = redis_image_ref
        self.timeout_raised = False

    def __call__(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = [str(arg) for arg in args]
        if _is_docker_image_inspect(argv, self._redis_image_ref):
            return _no_such_image_result(argv, self._redis_image_ref)
        if _is_docker_pull(argv, self._redis_image_ref):
            self.timeout_raised = True
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))
        return default_run(argv, **kwargs)


def _is_compose_up_detach_pull_never(argv: Sequence[str]) -> bool:
    """True for the lifecycle reconcile vector: compose up --detach --pull never."""
    return (
        len(argv) >= 6
        and argv[0] == "docker"
        and "compose" in argv
        and "up" in argv
        and "--detach" in argv
        and "--pull" in argv
        and "never" in argv
    )


class _ComposeUpPortRaceRun:
    """Test-scoped ``run`` seam: inject compose-up port-race stderr once path.

    Does not claim the daemon failed publish; only the adapter's run seam does.
    """

    def __init__(self) -> None:
        self.compose_up_injections = 0

    def __call__(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = [str(arg) for arg in args]
        if _is_compose_up_detach_pull_never(argv):
            self.compose_up_injections += 1
            return subprocess.CompletedProcess(
                args=argv,
                returncode=1,
                stdout="",
                stderr=(
                    "Error response from daemon: failed to set up container networking: "
                    "driver failed programming external connectivity on endpoint: "
                    "Bind for 127.0.0.1:0 failed: address already in use\n"
                ),
            )
        return default_run(argv, **kwargs)


def _probe_targets(
    project: RealComposeProject, secrets_map: Mapping[str, str]
) -> tuple[ProbeTarget, ...]:
    return (
        ProbeTarget(
            dependency=DependencyId.POSTGRES,
            host="127.0.0.1",
            port=project.ports["postgres"],
            username=project.username,
            database=project.database,
            secret=secrets_map["postgres"],
        ),
        ProbeTarget(
            dependency=DependencyId.REDIS,
            host="127.0.0.1",
            port=project.ports["redis"],
            db_number=0,
            secret=secrets_map["redis"],
        ),
        ProbeTarget(
            dependency=DependencyId.GRAFANA,
            host="127.0.0.1",
            port=project.ports["grafana"],
            secret=secrets_map["grafana"],
        ),
    )


class ImpostorListener:
    """Occupies one loopback port and records every byte it receives.

    The lifecycle's port preflight is bind-only and must never send protocol
    data to (or stop) an unrelated owner of the port; this listener proves it.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind((host, port))
        self._socket.listen(4)
        self._socket.settimeout(0.2)
        self.received = bytearray()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stopped.is_set():
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                connection.settimeout(0.5)
                try:
                    data = connection.recv(4096)
                    if data:
                        self.received.extend(data)
                except (TimeoutError, OSError):
                    pass
            finally:
                connection.close()

    def assert_untouched(self) -> None:
        assert bytes(self.received) == b"", (
            f"impostor on {self.host}:{self.port} received unexpected bytes: "
            f"{bytes(self.received)[:64]!r}"
        )

    def close(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=5)
        self._socket.close()


def test_cold_start_end_to_end_via_guarded_dispatch(
    real_compose_project_factory: RealComposeProjectFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    project = real_compose_project_factory.new()
    exit_code = real_compose_project_factory.run_guarded(project)
    assert exit_code == 0

    output = capsys.readouterr().out
    events = read_events_v2_jsonl(output)
    assert events, "guarded dispatch must emit v2 envelopes"
    for event in events:
        assert event["correlation_id"] == events[0]["correlation_id"]
    assert "\x1b[" not in output

    phases = [event["payload"]["phase"] for event in events]
    for expected in (
        "identity",
        "preflight",
        "lock",
        "image-pull",
        "image-verify",
        "reconcile",
        "readiness",
        "final",
    ):
        assert expected in phases

    readiness = {
        event["payload"].get("dependency"): event["payload"]
        for event in events
        if event["payload"]["phase"] == "readiness"
    }
    assert set(readiness) == {"postgres", "redis", "grafana"}
    assert all(payload["status"] == "PASSED" for payload in readiness.values())

    final = events[-1]["payload"]
    assert final["phase"] == "final"
    assert final["status"] == "PASSED"
    assert final["code"] == "OK"
    message = str(final["message"])
    for dependency in ("postgres", "redis", "grafana"):
        assert f"127.0.0.1:{project.ports[dependency]}" in message
    assert "@" not in message

    snapshot = real_compose_project_factory.snapshot(project)
    assert len(snapshot.containers) == 3
    assert len(snapshot.networks) == 1
    assert len(snapshot.volumes) == 2


async def test_missing_image_pull_is_reported_separately_before_readiness(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    """Simulate a redis inspect miss via test-scoped run seam, then real pull.

    Does not delete daemon images. The seam hides only the first redis
    ``image inspect`` until a successful real ``docker pull`` of the full
    redis ``image_ref``; the post-pull inspect and Os/Architecture/RepoDigests
    verification run against the real daemon. Pull/verify events must precede
    reconcile/readiness, with image timing excluded from the readiness window.
    """
    redis_ref = _assert_redis_image_ref_present(real_compose_project_factory)
    project = real_compose_project_factory.new()
    runner = _RedisInspectMissUntilPullRun(redis_ref)
    outcome = await real_compose_project_factory.start(
        project,
        adapter_factory=real_compose_project_factory.adapter_factory(run=runner),
    )
    assert outcome.status == "PASSED"
    assert runner.pull_succeeded, "redis pull must succeed to unhide inspect"

    pulls = {
        event["payload"]["dependency"]: event["payload"]
        for event in outcome.events
        if event["payload"]["phase"] == "image-pull"
    }
    assert set(pulls) == {"postgres", "redis", "grafana"}
    assert "pulled the reviewed pinned image digest" in str(pulls["redis"]["message"])
    assert pulls["redis"]["duration_ms"] >= 0
    assert "no registry access" in str(pulls["postgres"]["message"])
    assert "no registry access" in str(pulls["grafana"]["message"])

    phases = [event["payload"]["phase"] for event in outcome.events]
    last_verify = max(index for index, phase in enumerate(phases) if phase == "image-verify")
    first_reconcile = phases.index("reconcile")
    first_readiness = phases.index("readiness")
    assert (
        last_verify < first_reconcile < first_readiness
    ), "the readiness deadline starts only after image verification"
    assert readiness_window_seconds(outcome) <= 60.0

    snapshot = real_compose_project_factory.snapshot(project)
    assert len(snapshot.containers) == 3
    assert len(snapshot.volumes) == 2
    serialized = _serialized_outcome(outcome)
    for secret in project.secrets_map.values():
        assert secret not in serialized
    # Daemon cache untouched by the seam: redis image_ref remains inspectable.
    _assert_redis_image_ref_present(real_compose_project_factory)


async def test_missing_image_bounded_pull_failure_precedes_creation(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    """Simulate inspect miss + deterministic pull TimeoutExpired before create.

    A test-scoped run seam returns ``No such image`` for redis inspect and
    raises ``subprocess.TimeoutExpired`` for ``docker pull <redis image_ref>``
    so the adapter maps the bound to ``IMAGE_UNAVAILABLE`` without registry
    timing races or deleting local images. A subsequent default-adapter start
    must converge with all digests already local.
    """
    redis_ref = _assert_redis_image_ref_present(real_compose_project_factory)
    project = real_compose_project_factory.new()
    runner = _RedisInspectMissTimeoutPullRun(redis_ref)
    outcome = await real_compose_project_factory.start(
        project,
        adapter_factory=real_compose_project_factory.adapter_factory(
            run=runner,
            pull_timeout_seconds=0.5,
        ),
    )
    assert runner.timeout_raised, "pull path must raise subprocess.TimeoutExpired"
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "IMAGE_UNAVAILABLE"
    failures = [
        event["payload"]
        for event in outcome.events
        if event["payload"]["code"] == "IMAGE_UNAVAILABLE"
    ]
    assert failures, "expected an IMAGE_UNAVAILABLE image-pull event"
    assert failures[0]["dependency"] == "redis"
    assert failures[0]["phase"] == "image-pull"
    phases = [event["payload"]["phase"] for event in outcome.events]
    assert "reconcile" not in phases
    assert "readiness" not in phases
    snapshot = real_compose_project_factory.snapshot(project)
    assert not snapshot.containers
    assert not snapshot.networks
    assert not snapshot.volumes
    serialized = _serialized_outcome(outcome)
    for secret in project.secrets_map.values():
        assert secret not in serialized

    # Default adapter (no seam): image was never removed from the daemon.
    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"
    pull_messages = [
        str(event["payload"]["message"])
        for event in converged.events
        if event["payload"]["phase"] == "image-pull"
    ]
    assert len(pull_messages) == 3
    assert all("no registry access" in message for message in pull_messages)
    assert readiness_window_seconds(converged) <= 60.0
    _assert_redis_image_ref_present(real_compose_project_factory)


async def test_dynamic_loopback_ports_are_unique_and_loopback_bound(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    first = real_compose_project_factory.new()
    second = real_compose_project_factory.new()
    assert len(set(first.ports.values()) | set(second.ports.values())) == 6

    first_outcome = await real_compose_project_factory.start(first)
    second_outcome = await real_compose_project_factory.start(second)
    assert first_outcome.status == "PASSED"
    assert second_outcome.status == "PASSED"

    repo_path = str(real_compose_project_factory.repo_root)
    for project in (first, second):
        expected = {
            dependency.value: project.ports[dependency.value] for dependency in DependencyId
        }
        for container_id in real_compose_project_factory.snapshot(project).containers:
            document = json.loads(_docker(["inspect", container_id]).stdout)[0]
            bindings = document["HostConfig"]["PortBindings"]
            assert bindings, "each service must publish its container port"
            for entries in bindings.values():
                for entry in entries:
                    assert entry["HostIp"] == "127.0.0.1"
                    assert entry["HostPort"] in {str(port) for port in expected.values()}
            labels_blob = json.dumps(document["Config"]["Labels"])
            assert repo_path not in labels_blob
            assert (
                project.project_id == document["Config"]["Labels"]["com.tokenmarket.workspace-id"]
            )

    first_network = real_compose_project_factory.snapshot(first).networks
    second_network = real_compose_project_factory.snapshot(second).networks
    assert first_network != second_network


async def test_authenticated_host_probes_all_dependencies(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    project = real_compose_project_factory.new()
    outcome = await real_compose_project_factory.start(project)
    assert outcome.status == "PASSED"

    deadline = time.monotonic() + PROBE_DEADLINE_SECONDS
    targets = _probe_targets(project, project.secrets_map)
    results = await asyncio.gather(
        *(probe_dependency(target, deadline=deadline) for target in targets)
    )
    for result in results:
        assert result.readiness is ReadinessState.READY, result.safe_reason
        assert result.liveness is LivenessState.ALIVE

    connection = await asyncpg.connect(
        host="127.0.0.1",
        port=project.ports["postgres"],
        user=project.username,
        password=project.secrets_map["postgres"],
        database=project.database,
        timeout=PROBE_DEADLINE_SECONDS,
    )
    try:
        assert await connection.fetchval("SELECT 1") == 1
    finally:
        await connection.close()


async def test_project_network_probes_execute_real_protocols(
    real_compose_project_factory: RealComposeProjectFactory,
    network_probe_runner: NetworkProbeRunner,
) -> None:
    project = real_compose_project_factory.new()
    outcome = await real_compose_project_factory.start(project)
    assert outcome.status == "PASSED"

    postgres = network_probe_runner.probe_postgres(project)
    redis = network_probe_runner.probe_redis(project)
    grafana = network_probe_runner.probe_grafana(project)
    for evidence in (postgres, redis, grafana):
        assert evidence.exit_code == 0, f"{evidence.dependency}: {evidence.stderr}"
        assert evidence.matched, f"{evidence.dependency}: {evidence.stdout}"
        for secret in project.secrets_map.values():
            assert secret not in evidence.stdout
            assert secret not in evidence.stderr

    # Probe containers are short-lived; only compose containers (which carry
    # the tokenmarket repository label, never the tmtest one) may remain, so
    # the tmtest-LABEL scan must be empty after the probes exit.
    labeled = _docker(
        ["ps", "-aq", "--filter", "label=com.tokenmarket.repository=tmtest"]
    ).stdout.split()
    assert labeled == []


async def test_wrong_auth_host_and_network_probes_fail_safely(
    real_compose_project_factory: RealComposeProjectFactory,
    network_probe_runner: NetworkProbeRunner,
    synthetic_secret_factory: Any,
) -> None:
    project = real_compose_project_factory.new()
    outcome = await real_compose_project_factory.start(project)
    assert outcome.status == "PASSED"

    wrong = {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }
    deadline = time.monotonic() + PROBE_DEADLINE_SECONDS
    results = await asyncio.gather(
        *(probe_dependency(target, deadline=deadline) for target in _probe_targets(project, wrong))
    )
    expected_fields = {
        DependencyId.POSTGRES: "DATABASE_URL",
        DependencyId.REDIS: "REDIS_URL",
        DependencyId.GRAFANA: "GRAFANA_ADMIN_PASSWORD",
    }
    for result in results:
        assert result.readiness is ReadinessState.NOT_READY
        assert result.code == "DEPENDENCY_NOT_READY"
        assert expected_fields[result.dependency] in result.safe_reason
        assert len(result.safe_reason) <= 200
        for secret in (*wrong.values(), *project.secrets_map.values()):
            assert secret not in result.safe_reason

    redis_evidence = network_probe_runner.probe_redis(project, secret=wrong["redis"])
    assert not redis_evidence.matched
    grafana_evidence = network_probe_runner.probe_grafana(project, secret=wrong["grafana"])
    assert not grafana_evidence.matched
    postgres_evidence = network_probe_runner.probe_postgres(project, secret=wrong["postgres"])
    assert not postgres_evidence.matched
    for evidence in (redis_evidence, grafana_evidence, postgres_evidence):
        for secret in project.secrets_map.values():
            assert secret not in evidence.stdout
            assert secret not in evidence.stderr


async def test_credential_drift_fails_closed_retains_state_and_converges(
    real_compose_project_factory: RealComposeProjectFactory,
    synthetic_secret_factory: Any,
) -> None:
    project = real_compose_project_factory.new()
    first = await real_compose_project_factory.start(project)
    assert first.status == "PASSED"

    wrong_postgres = synthetic_secret_factory.new()
    drifted = await real_compose_project_factory.start(
        project,
        config_text=project.env_local_text_with(postgres_secret=wrong_postgres),
    )
    assert drifted.status == "FAILED"
    assert drifted.diagnostic_code == "DEPENDENCY_NOT_READY"
    readiness = {
        event["payload"].get("dependency"): event["payload"]
        for event in drifted.events
        if event["payload"]["phase"] == "readiness"
    }
    assert readiness["postgres"]["status"] == "FAILED"
    assert readiness["redis"]["status"] == "PASSED"
    assert readiness["grafana"]["status"] == "PASSED"
    postgres_reason = str(readiness["postgres"]["message"])
    assert "DATABASE_URL" in postgres_reason

    serialized = _serialized_outcome(drifted)
    assert wrong_postgres not in serialized
    for secret in project.secrets_map.values():
        assert secret not in serialized

    # Failure retains inspectable project state and every named volume.
    retained = real_compose_project_factory.snapshot(project)
    assert len(retained.containers) == 3
    assert len(retained.networks) == 1
    assert len(retained.volumes) == 2

    # Fixing the reported cause (the original persisted credential) converges.
    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"


async def test_port_conflict_names_dependency_before_creation_and_spares_impostor(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    project = real_compose_project_factory.new()
    impostor = ImpostorListener("127.0.0.1", project.ports["grafana"])
    try:
        outcome = await real_compose_project_factory.start(project)
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "PORT_CONFLICT"
        conflicts = [
            event["payload"]
            for event in outcome.events
            if event["payload"]["code"] == "PORT_CONFLICT"
        ]
        assert conflicts, "expected a PORT_CONFLICT event"
        assert conflicts[0]["dependency"] == "grafana"
        assert str(project.ports["grafana"]) in str(conflicts[0]["message"])

        # Clean-start conflict: nothing was created for any dependency.
        snapshot = real_compose_project_factory.snapshot(project)
        assert not snapshot.containers
        assert not snapshot.networks
        assert not snapshot.volumes

        # No credential or probe traffic ever reached the impostor; it was
        # never stopped by the lifecycle.
        impostor.assert_untouched()
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.connect(("127.0.0.1", project.ports["grafana"]))
        finally:
            probe.close()
    finally:
        impostor.close()

    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"


async def test_port_bind_race_during_reconcile_is_classified_and_retained(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    """Classify a reconcile-time port race via test-scoped compose-up injection.

    Docker Desktop / WSL2 port namespaces do not reliably surface a real
    compose publish failure when a WSL ImpostorListener holds the loopback
    port, so this test injects compose-up stderr containing a product
    ``_PORT_RACE_MARKERS`` phrase through a test-scoped ``run`` seam. It does
    **not** claim the daemon itself failed to publish. ImpostorListener plus
    real ``default_bind_check`` after the first six preflight skips still prove
    attribution and that the lifecycle never touches the port owner.
    """
    project = real_compose_project_factory.new()
    impostors = [
        ImpostorListener("127.0.0.1", project.ports[dependency])
        for dependency in ("postgres", "redis", "grafana")
    ]
    bind_calls = {"count": 0}
    compose_run = _ComposeUpPortRaceRun()

    def scripted_bind_check(host: str, port: int) -> None:
        bind_calls["count"] += 1
        if bind_calls["count"] <= 6:
            # The two preflight rounds (three dependencies each) pass so the
            # conflict is classified only after the injected compose-up race;
            # the attribution re-checks afterwards use the real bind check.
            return
        default_bind_check(host, port)

    try:
        outcome = await real_compose_project_factory.start(
            project,
            adapter_factory=real_compose_project_factory.adapter_factory(
                bind_check=scripted_bind_check,
                run=compose_run,
            ),
        )
        assert (
            compose_run.compose_up_injections == 1
        ), "exactly one compose up --detach --pull never injection is expected"
        assert (
            bind_calls["count"] > 6
        ), "attribution must invoke real bind_check after the six preflight skips"
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "PORT_CONFLICT"
        conflicts = [
            event["payload"]
            for event in outcome.events
            if event["payload"]["code"] == "PORT_CONFLICT"
        ]
        assert conflicts, "expected a reconcile-time PORT_CONFLICT event"
        assert conflicts[0]["phase"] == "reconcile"
        assert conflicts[0]["dependency"] == "postgres"
        assert "reconcile" in str(conflicts[0]["message"])

        # Failed reconcile retains inspectable project state (may be empty if
        # compose up never mutated); never cleans up on failure.
        retained = real_compose_project_factory.snapshot(project)
        assert len(retained.containers) <= 3
        assert len(retained.volumes) <= 2
        for impostor in impostors:
            impostor.assert_untouched()
    finally:
        for impostor in impostors:
            impostor.close()

    # Default adapter (no run/bind seams): ports free after impostors close.
    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"
    assert (
        compose_run.compose_up_injections == 1
    ), "converged start must not reuse the injected compose-up run seam"
    final = real_compose_project_factory.snapshot(project)
    assert len(final.containers) == 3
    assert len(final.volumes) == 2


async def test_converges_from_stopped_and_partial_states(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    project = real_compose_project_factory.new()
    first = await real_compose_project_factory.start(project)
    assert first.status == "PASSED"
    services = _container_ids_by_service(project)
    assert set(services) == {"postgres", "redis", "grafana"}

    # Stopped state: an externally stopped container is reconciled in place.
    _docker(["stop", services["redis"]])
    second = await real_compose_project_factory.start(project)
    assert second.status == "PASSED"
    after_stop = _container_ids_by_service(project)
    assert after_stop == services

    # Partial state: one container removed outright; rerun recreates exactly
    # it while every other identity stays stable. A graceful stop releases
    # the published port synchronously (Docker Desktop holds it for tens of
    # seconds after a force remove); the short wait is only a safety net.
    _docker(["stop", services["grafana"]])
    _docker(["rm", services["grafana"]])
    _wait_port_free(project.ports["grafana"])
    third = await real_compose_project_factory.start(project)
    assert third.status == "PASSED"
    after_partial = _container_ids_by_service(project)
    assert set(after_partial) == {"postgres", "redis", "grafana"}
    assert after_partial["grafana"] != services["grafana"]
    assert after_partial["postgres"] == services["postgres"]
    assert after_partial["redis"] == services["redis"]
    snapshot = real_compose_project_factory.snapshot(project)
    assert len(snapshot.containers) == 3
    assert len(snapshot.networks) == 1
    assert len(snapshot.volumes) == 2

    # All-stopped state: the whole project converges without duplicates. A
    # stopped container's host forwarder lingers on Docker Desktop (measured
    # ~25 s), so the test waits for the ports before rerunning.
    for container_id in after_partial.values():
        _docker(["stop", container_id])
    for port in project.ports.values():
        _wait_port_free(port)
    fourth = await real_compose_project_factory.start(project)
    assert fourth.status == "PASSED"
    final = real_compose_project_factory.snapshot(project)
    assert len(final.containers) == 3
    assert len(final.networks) == 1
    assert len(final.volumes) == 2


async def test_daemon_loss_reports_stable_redacted_diagnostic_without_mutation(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    project = real_compose_project_factory.new()
    # Daemon loss is injected at the process-environment level because the
    # adapter's read-only preflight subprocesses inherit it; the value is
    # restored before any other test or teardown runs.
    saved = os.environ.get("DOCKER_HOST")
    os.environ["DOCKER_HOST"] = "unix:///nonexistent/tmtest-dead-daemon.sock"
    try:
        outcome = await real_compose_project_factory.start(project)
    finally:
        if saved is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = saved

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "TOOL_VERSION_UNSUPPORTED"
    assert "unreachable" in outcome.message

    serialized = _serialized_outcome(outcome)
    assert "tmtest-dead-daemon" not in serialized
    for secret in project.secrets_map.values():
        assert secret not in serialized

    # The read-only preflight fails before coordination metadata or mutation.
    assert not (project.runtime_base / project.project_id).exists()
    snapshot = real_compose_project_factory.snapshot(project)
    assert not snapshot.containers
    assert not snapshot.networks
    assert not snapshot.volumes
    assert os.environ.get("DOCKER_HOST") == saved

    # The diagnostic run had zero side effects: a normal start converges.
    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"


async def test_readiness_timeout_classification_retains_resources_and_converges(
    real_compose_project_factory: RealComposeProjectFactory,
) -> None:
    project = real_compose_project_factory.new()

    async def exhausted_probe(target: ProbeTarget, deadline: float) -> DependencyHealthResult:
        # Real timeout classification: the genuine probe path reports the
        # stable timeout category without any network access once no time
        # remains in the shared deadline.
        return await probe_dependency(target, deadline=time.monotonic() - 1.0)

    outcome = await real_compose_project_factory.start(project, probe_fn=exhausted_probe)
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "DEPENDENCY_NOT_READY"
    assert "60-second" in outcome.message
    assert len(outcome.dependency_results) == 3
    for result in outcome.dependency_results:
        assert result.readiness is ReadinessState.NOT_READY
        assert result.code == "DEPENDENCY_NOT_READY"
        assert "deadline" in result.safe_reason

    # Timed-out state is retained and inspectable; nothing is cleaned up.
    retained = real_compose_project_factory.snapshot(project)
    assert len(retained.containers) == 3
    assert len(retained.networks) == 1
    assert len(retained.volumes) == 2

    converged = await real_compose_project_factory.start(project)
    assert converged.status == "PASSED"
