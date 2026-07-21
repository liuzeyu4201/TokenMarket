"""Dirty-worktree preservation tests for the SF02 lifecycle (T036, US2).

Covers the workspace-preservation rule of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and quickstart section 10: running ``dev`` and ``dev-down`` must never create,
modify, delete, or re-permission ANY worktree file — dirty tracked files,
untracked files, symlinks, or the ignored secret-bearing ``.env.local``. The
lifecycle may write only below its secure per-user runtime base, which lives
outside the workspace.

A synthetic worktree (never the real repository checkout) is snapshot before
and after each operation — relative path, entry kind, content hash, mode, and
symlink target — and the snapshots must be identical. The real-Compose
negative assertions of T067 extend this file later; everything here runs
through fake adapter seams with no Docker access.

The ``dev`` path already exists (T031); the ``dev-down`` orchestration is
implemented by T044 in ``tools/workflow/local_env/lifecycle.py`` and the
guarded dispatch by T049, so the down tests fail with an explicit
not-implemented guard until then.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from workflow.local_env import compose as compose_module
from workflow.local_env import models as models_module

from .conftest import TEST_REPOSITORY_LABEL, MonotonicClock
from .helpers import load_json

SENTINEL_WORKSPACE_PATH = "/sf02-dirty-worktree-sentinel"
WORKTREE_PORTS = {"postgres": 25432, "redis": 26379, "grafana": 23000}


def _lifecycle_down() -> Any:
    lifecycle = importlib.import_module("workflow.local_env.lifecycle")
    if not hasattr(lifecycle, "stop_local_environment"):
        pytest.fail(
            "workflow.local_env.lifecycle.stop_local_environment is not " "implemented yet (T044)"
        )
    return lifecycle


def _lifecycle_start() -> Any:
    return importlib.import_module("workflow.local_env.lifecycle")


@pytest.fixture(scope="module")
def manifest() -> Any:
    return models_module.parse_manifest(load_json("ops", "workflow", "local-dependencies.json"))


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


def _config_text(secrets_map: Mapping[str, str]) -> str:
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://devuser:{secrets_map['postgres']}@"
        f"127.0.0.1:{WORKTREE_PORTS['postgres']}/appdb\n"
        f"REDIS_URL=redis://default:{secrets_map['redis']}@"
        f"127.0.0.1:{WORKTREE_PORTS['redis']}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{WORKTREE_PORTS['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets_map['grafana']}\n"
    )


def _write_worktree(root: Path, config_text: str) -> None:
    """Create a synthetic worktree with dirty/untracked/symlink entries."""
    (root / "nested" / "deeper").mkdir(parents=True)
    (root / "tracked-clean.txt").write_text("clean content\n", encoding="utf-8")
    (root / "tracked-dirty.txt").write_text("locally modified content\n", encoding="utf-8")
    (root / "untracked-notes.log").write_text("scratch\n", encoding="utf-8")
    (root / ".env.local").write_text(config_text, encoding="utf-8")
    (root / "nested" / "deeper" / "module.py").write_text("print('untouched')\n", encoding="utf-8")
    (root / "link-to-clean").symlink_to("tracked-clean.txt")
    (root / "dangling-link").symlink_to("missing-target.txt")


def _snapshot(root: Path) -> dict[str, tuple[str, str]]:
    """Capture kind+content/mode/target of every entry below ``root``."""
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        entry_stat = os.lstat(path)
        if stat.S_ISLNK(entry_stat.st_mode):
            result[relative] = ("symlink", os.readlink(path))
        elif stat.S_ISDIR(entry_stat.st_mode):
            result[relative] = ("dir", oct(stat.S_IMODE(entry_stat.st_mode)))
        elif stat.S_ISREG(entry_stat.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[relative] = (
                "file",
                f"{digest}:{oct(stat.S_IMODE(entry_stat.st_mode))}",
            )
        else:
            result[relative] = ("other", "")
    return result


class _WorktreeWorld:
    """Minimal scripted Compose-facing world for the synthetic worktree."""

    def __init__(self, clock: MonotonicClock) -> None:
        self.clock = clock
        self.calls: list[str] = []
        self.containers: dict[str, str] = {}
        self.networks: dict[str, str] = {}
        self.volumes: dict[str, str] = {}

    def log(self, name: str) -> None:
        self.calls.append(name)

    def seed_running(self, project_id: str) -> None:
        for service in ("postgres", "redis", "grafana"):
            self.containers[service] = f"{service}-container-0001"
        self.networks["default"] = "default-network-0001"
        self.volumes["postgres-data"] = f"{project_id}_postgres-data"
        self.volumes["redis-data"] = f"{project_id}_redis-data"


class _FakeResource:
    """Duck-typed exact-label resource record for the down surface."""

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


class _WorktreeAdapter:
    """Fake adapter implementing both the start and the down surfaces."""

    def __init__(self, world: _WorktreeWorld, manifest: Any, identity: Any) -> None:
        self._world = world
        self._manifest = manifest
        self._identity = identity

    # -- start surface (T031 protocol) ----------------------------------------

    def verify_runtime(self) -> Any:
        self._world.log("verify_runtime")
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
        return ()

    def assert_exact_ownership(self, state: Any) -> None:
        self._world.log("assert_exact_ownership")

    def assert_no_workspace_path_in_labels(self, state: Any) -> None:
        self._world.log("assert_no_workspace_path_in_labels")

    def assert_loopback_publishers(self, state: Any) -> None:
        self._world.log("assert_loopback_publishers")

    def preflight_ports(self, state: Any, desired_ports: Mapping[Any, int]) -> None:
        self._world.log("preflight_ports")

    def ensure_images(self, runtime: Any) -> tuple[Any, ...]:
        self._world.log("ensure_images")
        return tuple(
            compose_module.ImagePullRecord(dependency=definition.id, pulled=False)
            for definition in self._manifest.dependencies
        )

    def reconcile_up(
        self,
        secrets: Any,
        *,
        timeout_seconds: float,
        derived_env: Mapping[str, str] | None = None,
    ) -> None:
        self._world.log("reconcile_up")

    # -- down surface (T044 protocol) ------------------------------------------

    def _labels(self, service: str | None = None) -> dict[str, str]:
        labels = {
            "com.tokenmarket.repository": TEST_REPOSITORY_LABEL,
            "com.tokenmarket.workspace-id": self._identity.project_id,
            "com.tokenmarket.workspace-fingerprint": self._identity.workspace_fingerprint,
        }
        if service is not None:
            labels["com.docker.compose.service"] = service
        return labels

    def project_resources(self) -> tuple[Any, ...]:
        self._world.log("project_resources")
        resources: list[Any] = []
        for service, container_id in sorted(self._world.containers.items()):
            resources.append(
                _FakeResource(
                    "container",
                    container_id,
                    f"{self._identity.project_id}-{service}-1",
                    self._labels(service),
                )
            )
        for network_id in sorted(self._world.networks.values()):
            resources.append(
                _FakeResource(
                    "network",
                    network_id,
                    f"{self._identity.project_id}_default",
                    self._labels(),
                )
            )
        for logical, volume_name in sorted(self._world.volumes.items()):
            resources.append(_FakeResource("volume", volume_name, volume_name, self._labels()))
        return tuple(resources)

    def repository_resources(self) -> tuple[Any, ...]:
        self._world.log("repository_resources")
        return ()

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
        self._world.log("reconcile_down")
        self._world.containers.clear()
        self._world.networks.clear()


def _world_factory(world: _WorktreeWorld) -> Any:
    def factory(manifest: Any, identity: Any, project_dir: Path, repo_root: Path) -> Any:
        world.log("factory")
        return _WorktreeAdapter(world, manifest, identity)

    return factory


async def _ready_probe(target: Any, deadline: float) -> Any:
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


async def _run_dev(
    *,
    workspace: Path,
    world: _WorktreeWorld,
    config_text: str,
    manifest: Any,
    runtime_base: Path,
    clock: MonotonicClock,
) -> Any:
    lifecycle = _lifecycle_start()

    async def sleep(seconds: float) -> None:
        clock.advance(seconds)

    return await lifecycle.start_local_environment(
        repo_root=workspace,
        workspace_root=workspace,
        config_reader=lambda: config_text,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=_world_factory(world),
        probe_fn=_ready_probe,
        clock=clock,
        sleep=sleep,
    )


async def _run_down(
    *,
    workspace: Path,
    world: _WorktreeWorld,
    manifest: Any,
    runtime_base: Path,
    clock: MonotonicClock,
) -> Any:
    lifecycle = _lifecycle_down()
    return await lifecycle.stop_local_environment(
        repo_root=workspace,
        workspace_root=workspace,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=_world_factory(world),
        clock=clock,
    )


async def test_dev_preserves_dirty_worktree(
    tmp_path: Path,
    synthetic_secret_factory: Any,
    runtime_base: Path,
    manifest: Any,
    monotonic_clock: MonotonicClock,
) -> None:
    secrets_map = {
        name: synthetic_secret_factory.new() for name in ("postgres", "redis", "grafana")
    }
    config_text = _config_text(secrets_map)
    workspace = tmp_path / "worktree"
    _write_worktree(workspace, config_text)
    before = _snapshot(workspace)
    world = _WorktreeWorld(monotonic_clock)

    outcome = await _run_dev(
        workspace=workspace,
        world=world,
        config_text=config_text,
        manifest=manifest,
        runtime_base=runtime_base,
        clock=monotonic_clock,
    )

    assert outcome.status == "PASSED"
    assert _snapshot(workspace) == before, "make dev must not touch any worktree file"


async def test_dev_down_preserves_dirty_worktree(
    tmp_path: Path,
    synthetic_secret_factory: Any,
    runtime_base: Path,
    manifest: Any,
    monotonic_clock: MonotonicClock,
) -> None:
    secrets_map = {
        name: synthetic_secret_factory.new() for name in ("postgres", "redis", "grafana")
    }
    config_text = _config_text(secrets_map)
    workspace = tmp_path / "worktree"
    _write_worktree(workspace, config_text)
    before = _snapshot(workspace)
    world = _WorktreeWorld(monotonic_clock)
    identity_module = importlib.import_module("workflow.local_env.identity")
    identity = identity_module.workspace_identity(workspace)
    world.seed_running(identity.project_id)

    outcome = await _run_down(
        workspace=workspace,
        world=world,
        manifest=manifest,
        runtime_base=runtime_base,
        clock=monotonic_clock,
    )

    assert outcome.status == "PASSED"
    assert (
        _snapshot(workspace) == before
    ), "make dev-down must not touch any worktree file, including .env.local"


async def test_dev_then_dev_down_cycle_preserves_everything(
    tmp_path: Path,
    synthetic_secret_factory: Any,
    runtime_base: Path,
    manifest: Any,
    monotonic_clock: MonotonicClock,
) -> None:
    secrets_map = {
        name: synthetic_secret_factory.new() for name in ("postgres", "redis", "grafana")
    }
    config_text = _config_text(secrets_map)
    workspace = tmp_path / "worktree"
    _write_worktree(workspace, config_text)
    before = _snapshot(workspace)
    world = _WorktreeWorld(monotonic_clock)

    dev_outcome = await _run_dev(
        workspace=workspace,
        world=world,
        config_text=config_text,
        manifest=manifest,
        runtime_base=runtime_base,
        clock=monotonic_clock,
    )
    assert dev_outcome.status == "PASSED"
    assert _snapshot(workspace) == before, "dev modified the worktree"

    identity_module = importlib.import_module("workflow.local_env.identity")
    identity = identity_module.workspace_identity(workspace)
    world.seed_running(identity.project_id)
    down_outcome = await _run_down(
        workspace=workspace,
        world=world,
        manifest=manifest,
        runtime_base=runtime_base,
        clock=monotonic_clock,
    )
    assert down_outcome.status == "PASSED"
    assert _snapshot(workspace) == before, "dev-down modified the worktree"

    second_down = await _run_down(
        workspace=workspace,
        world=world,
        manifest=manifest,
        runtime_base=runtime_base,
        clock=monotonic_clock,
    )
    assert second_down.status == "PASSED"
    assert _snapshot(workspace) == before, "a repeated dev-down modified the worktree"
