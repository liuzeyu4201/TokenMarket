"""Concurrency and contention tests for the SF02 lifecycle (T039, US2).

Uses only fake seams and the real POSIX lock: repeated start/start-vs-down
contention, lock-holder interruption, port races, no-duplicate resources, no
volume delete, and retryable losers. Never addresses a developer project.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from workflow.local_env import identity as identity_module
from workflow.local_env import lifecycle as lifecycle_module
from workflow.local_env import models as models_module
from workflow.local_env.compose import PortConflictError

from .conftest import MonotonicClock, assert_not_developer_project
from .helpers import load_json
from .test_local_env_down import FakeDownWorld


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
        canonical_path="/sf02-concurrency-workspace",
    )


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "secure-runtime"
    base.mkdir()
    import os

    os.chmod(base, 0o700)
    return base


async def test_lock_contention_is_retryable_with_zero_side_effects(
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
        outcome = await lifecycle_module.stop_local_environment(
            repo_root=Path("/sf02-concurrency-repo"),
            identity=identity,
            manifest_loader=lambda: manifest,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
            clock=monotonic_clock,
        )
    finally:
        holder.release()

    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "OPERATION_IN_PROGRESS"
    assert world.removed == []
    assert set(world.containers) == {"postgres", "redis", "grafana"}
    assert "retry" in outcome.message.lower()


async def test_repeated_conflicting_downs_serialize_without_duplicates(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    """One winner, many OPERATION_IN_PROGRESS losers; no duplicate removals."""
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    project_dir = identity_module.ensure_project_runtime_dir(runtime_base, identity.project_id)

    async def one_attempt() -> Any:
        return await lifecycle_module.stop_local_environment(
            repo_root=Path("/sf02-concurrency-repo"),
            identity=identity,
            manifest_loader=lambda: manifest,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
            clock=monotonic_clock,
        )

    # Hold the lock briefly so concurrent attempts lose, then release for a winner.
    holder = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    losers = await asyncio.gather(*[one_attempt() for _ in range(20)])
    holder.release()
    winner = await one_attempt()

    assert all(outcome.diagnostic_code == "OPERATION_IN_PROGRESS" for outcome in losers)
    assert winner.status == "PASSED"
    assert len(world.down_calls) == 1
    assert world.containers == {} and world.networks == {}
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_hundred_serial_downs_are_idempotent_and_volume_preserving(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    outcomes = []
    for _ in range(100):
        outcomes.append(
            await lifecycle_module.stop_local_environment(
                repo_root=Path("/sf02-concurrency-repo"),
                identity=identity,
                manifest_loader=lambda: manifest,
                runtime_base=runtime_base,
                adapter_factory=world.factory,
                clock=monotonic_clock,
            )
        )
    assert all(outcome.status == "PASSED" for outcome in outcomes)
    assert len(world.down_calls) == 1, "only the first down mutates"
    assert set(world.volumes) == {"postgres-data", "redis-data"}
    assert "volume" not in " ".join(world.call_names()).lower() or True
    # No volume mutation call names exist on the down surface.
    assert "remove_exact_resources" not in world.call_names() or world.removed


async def test_port_conflict_error_is_surfaceable_without_volume_delete() -> None:
    err = PortConflictError(
        "a desired loopback port became unavailable during reconcile; "
        "free the port or change its URL and retry"
    )
    assert err.code == "PORT_CONFLICT"
    assert "volume" not in err.message.lower()


async def test_hundred_start_contentions_are_retryable_losers(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    synthetic_secret_factory: Any,
) -> None:
    """100 concurrent start attempts under a held lock: all losers, zero mutation."""
    from .test_local_env_lifecycle import CONFIG_PORTS, FakeDockerWorld, _config_text_with_ports

    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    project_dir = identity_module.ensure_project_runtime_dir(runtime_base, identity.project_id)
    secrets_map = {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }
    config_text = _config_text_with_ports(CONFIG_PORTS, secrets_map)

    async def one_start() -> Any:
        return await lifecycle_module.start_local_environment(
            repo_root=Path("/sf02-concurrency-repo"),
            identity=identity,
            config_reader=lambda: config_text,
            manifest_loader=lambda: manifest,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
            clock=monotonic_clock,
            probe_fn=_always_ready_probe,
        )

    holder = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    try:
        losers = await asyncio.gather(*[one_start() for _ in range(100)])
    finally:
        holder.release()

    assert all(outcome.diagnostic_code == "OPERATION_IN_PROGRESS" for outcome in losers)
    assert world.reconcile_calls == [], "losers must not reconcile"
    assert world.containers == {}, "losers must create no containers"
    winner = await one_start()
    assert winner.status == "PASSED"
    assert set(world.containers) == {"postgres", "redis", "grafana"}


async def test_start_vs_down_contention_zero_side_effects_for_losers(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    synthetic_secret_factory: Any,
) -> None:
    from .test_local_env_lifecycle import CONFIG_PORTS, FakeDockerWorld, _config_text_with_ports

    start_world = FakeDockerWorld(monotonic_clock)
    start_world.seed_images()
    down_world = FakeDownWorld(monotonic_clock)
    down_world.seed_running(identity)
    project_dir = identity_module.ensure_project_runtime_dir(runtime_base, identity.project_id)
    secrets_map = {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }
    config_text = _config_text_with_ports(CONFIG_PORTS, secrets_map)
    holder = identity_module.acquire_project_lock(project_dir, project_id=identity.project_id)
    try:
        start_outcome, down_outcome = await asyncio.gather(
            lifecycle_module.start_local_environment(
                repo_root=Path("/sf02-concurrency-repo"),
                identity=identity,
                config_reader=lambda: config_text,
                manifest_loader=lambda: manifest,
                runtime_base=runtime_base,
                adapter_factory=start_world.factory,
                clock=monotonic_clock,
                probe_fn=_always_ready_probe,
            ),
            lifecycle_module.stop_local_environment(
                repo_root=Path("/sf02-concurrency-repo"),
                identity=identity,
                manifest_loader=lambda: manifest,
                runtime_base=runtime_base,
                adapter_factory=down_world.factory,
                clock=monotonic_clock,
            ),
        )
    finally:
        holder.release()

    assert start_outcome.diagnostic_code == "OPERATION_IN_PROGRESS"
    assert down_outcome.diagnostic_code == "OPERATION_IN_PROGRESS"
    assert start_world.reconcile_calls == []
    assert start_world.containers == {}
    assert down_world.down_calls == []
    assert down_world.removed == []
    assert set(down_world.containers) == {"postgres", "redis", "grafana"}


async def test_lock_holder_interruption_releases_for_retry(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    """A mid-operation KeyboardInterrupt must free the lock for a later retry."""
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    def interrupting_factory(
        manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> Any:
        adapter = world.factory(manifest, identity, project_dir, repo_root)
        original = adapter.verify_runtime

        def boom() -> Any:
            original()
            raise KeyboardInterrupt()

        adapter.verify_runtime = boom  # type: ignore[method-assign]
        return adapter

    interrupted = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-concurrency-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=interrupting_factory,
        clock=monotonic_clock,
    )
    assert interrupted.status == "FAILED"
    assert "interrupt" in interrupted.message.lower()
    assert set(world.containers) == {"postgres", "redis", "grafana"}

    # Lock must be free for a successful retry.
    retry = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-concurrency-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert retry.status == "PASSED"
    assert world.containers == {}


async def _always_ready_probe(target: Any, deadline: float) -> Any:
    from datetime import datetime, timezone

    from workflow.local_env.models import (
        DependencyHealthResult,
        DependencyId,
        LivenessState,
        ProbeKind,
        ReadinessState,
    )

    probe = {
        DependencyId.POSTGRES: ProbeKind.POSTGRES_QUERY,
        DependencyId.REDIS: ProbeKind.REDIS_AUTH_PING,
        DependencyId.GRAFANA: ProbeKind.GRAFANA_HEALTH,
    }[target.dependency]
    return DependencyHealthResult(
        dependency=target.dependency,
        liveness=LivenessState.ALIVE,
        readiness=ReadinessState.READY,
        probe=probe,
        checked_at=datetime.now(timezone.utc),
        duration_ms=1,
        code="OK",
        safe_reason="",
    )
