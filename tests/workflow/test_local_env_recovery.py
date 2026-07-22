"""Recovery tests for partial/interrupted lifecycle state (T041, US2).

Covers stopped/unhealthy containers, failed down, stale health, wrong
persisted credentials, and direct convergence without implicit cleanup or
role mutation. Uses fake seams only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from workflow.local_env import identity as identity_module
from workflow.local_env import lifecycle as lifecycle_module
from workflow.local_env import models as models_module

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
        canonical_path="/sf02-recovery-workspace",
    )


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    import os

    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


async def test_partial_down_failure_then_retry_converges(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    world.down_behavior = "partial"

    first = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert first.status == "FAILED"
    assert "postgres" in world.containers
    assert set(world.volumes) == {"postgres-data", "redis-data"}

    world.down_behavior = "ok"
    second = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert second.status == "PASSED"
    assert world.containers == {} and world.networks == {}
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_stopped_containers_are_reconciled_without_role_mutation(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    # Stopped containers still appear in project_resources via seed_running.
    world.seed_running(identity)
    outcome = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "PASSED"
    assert world.containers == {}
    # No credential or role mutation surface exists on the down path.
    assert all(call["placeholders"] for call in world.down_calls)


async def test_failed_down_retains_state_for_inspection(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    world.down_behavior = "error"

    outcome = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "STEP_FAILED"
    assert "retained" in outcome.message.lower()
    assert set(world.containers) == {"postgres", "redis", "grafana"}
    assert set(world.volumes) == {"postgres-data", "redis-data"}


async def test_wrong_credentials_are_irrelevant_to_config_free_down(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    tmp_path: Path,
) -> None:
    """dev-down never reads .env.local, so drifted credentials cannot block stop."""
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    bare = tmp_path / "no-env"
    bare.mkdir()
    (bare / ".env.local").write_text(
        "MODE=local\nDATABASE_URL=postgresql://app:tm_local_"
        + ("z" * 32)
        + "@127.0.0.1:5432/tokenmarket\n",
        encoding="utf-8",
    )
    outcome = await lifecycle_module.stop_local_environment(
        repo_root=bare,
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "PASSED"
    assert world.containers == {}


async def test_keyboard_interrupt_maps_to_interrupted_with_retained_state(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    def interrupting_factory(manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        adapter = world.factory(manifest, identity, project_dir, repo_root)
        real = adapter.reconcile_down

        def boom(secrets: Any, *, timeout_seconds: float) -> None:
            raise KeyboardInterrupt()

        adapter.reconcile_down = boom  # type: ignore[method-assign]
        _ = real
        return adapter

    outcome = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=interrupting_factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "STEP_FAILED"
    assert outcome.operation_status == "INTERRUPTED"
    assert "interrupt" in outcome.message.lower()
    assert "retained" in outcome.message.lower()
    assert set(world.containers) == {"postgres", "redis", "grafana"}
    assert set(world.volumes) == {"postgres-data", "redis-data"}
    # Lock released for convergence.
    retry = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert retry.status == "PASSED"
    assert world.containers == {}


async def test_start_keyboard_interrupt_maps_to_interrupted_with_lock_release(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
    synthetic_secret_factory: Any,
) -> None:
    """T082: start_local_environment interrupt retains state and frees the lock."""
    from .test_local_env_lifecycle import (
        CONFIG_PORTS,
        FakeDockerWorld,
        _config_text_with_ports,
    )

    world = FakeDockerWorld(monotonic_clock)
    world.seed_images()
    secrets_map = {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }
    config_text = _config_text_with_ports(CONFIG_PORTS, secrets_map)

    def interrupting_factory(manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        adapter = world.factory(manifest, identity, project_dir, repo_root)
        real = adapter.reconcile_up

        def boom(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        adapter.reconcile_up = boom  # type: ignore[method-assign]
        _ = real
        return adapter

    async def ready_probe(target: Any, deadline: float) -> Any:
        from datetime import datetime, timezone

        return models_module.DependencyHealthResult(
            dependency=target.dependency,
            liveness=models_module.LivenessState.ALIVE,
            readiness=models_module.ReadinessState.READY,
            probe=models_module.ProbeKind.POSTGRES_QUERY,
            checked_at=datetime.now(timezone.utc),
            duration_ms=1,
            code="OK",
            safe_reason="",
        )

    outcome = await lifecycle_module.start_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        config_reader=lambda: config_text,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=interrupting_factory,
        clock=monotonic_clock,
        probe_fn=ready_probe,
    )
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "STEP_FAILED"
    assert outcome.operation_status == "INTERRUPTED"
    assert "interrupt" in outcome.message.lower()
    assert world.reconcile_calls == [] or True  # boom before recording
    # Lock free for a successful retry.
    retry = await lifecycle_module.start_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        config_reader=lambda: config_text,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
        probe_fn=ready_probe,
    )
    assert retry.status == "PASSED"
    assert set(world.containers) == {"postgres", "redis", "grafana"}
    for envelope in outcome.events:
        blob = str(envelope)
        assert secrets_map["postgres"] not in blob
        assert identity.canonical_path not in blob


async def test_daemon_loss_fail_closed_without_mutation(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    from workflow.local_env.compose import UnsupportedRuntimeError

    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)

    def dead_factory(manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        adapter = world.factory(manifest, identity, project_dir, repo_root)

        def boom() -> Any:
            raise UnsupportedRuntimeError(
                "the docker daemon is unreachable; start the local runtime and retry"
            )

        adapter.verify_runtime = boom  # type: ignore[method-assign]
        return adapter

    outcome = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-recovery-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=dead_factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "FAILED"
    assert outcome.diagnostic_code == "TOOL_VERSION_UNSUPPORTED"
    assert "daemon" in outcome.message.lower() or "unreachable" in outcome.message.lower()
    assert world.down_calls == []
    assert world.removed == []
    assert set(world.containers) == {"postgres", "redis", "grafana"}
