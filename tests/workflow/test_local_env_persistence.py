"""Persistence cycle tests for SF02 stop/start (T040/T076, US2).

Fake adapter cycles prove volume identity stability. Real-Compose cycles
(when Docker is available) write a PostgreSQL marker and verify retention
across ten start/down/restart rounds.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from workflow.local_env import identity as identity_module
from workflow.local_env import lifecycle as lifecycle_module
from workflow.local_env import models as models_module
from workflow.local_env.models import DependencyId

from .conftest import (
    MonotonicClock,
    NetworkProbeRunner,
    RealComposeProjectFactory,
    assert_not_developer_project,
    postgres_marker_query_sql,
    postgres_marker_sql,
    redis_reset_is_allowed,
)
from .helpers import load_json
from .test_local_env_down import FakeDownWorld
from .test_local_env_integration import _wait_port_free


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
        canonical_path="/sf02-persistence-workspace",
    )


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    import os

    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


async def test_ten_down_restart_cycles_retain_named_volumes(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    marker_volume_ids = dict(world.volumes)

    for cycle in range(10):
        down = await lifecycle_module.stop_local_environment(
            repo_root=Path("/sf02-persistence-repo"),
            identity=identity,
            manifest_loader=lambda: manifest,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
            clock=monotonic_clock,
        )
        assert down.status == "PASSED", f"cycle {cycle} down failed"
        assert world.containers == {} and world.networks == {}
        assert world.volumes == marker_volume_ids
        world.seed_running(identity)
        assert world.volumes == marker_volume_ids

    assert set(marker_volume_ids) == {"postgres-data", "redis-data"}
    assert "grafana" not in world.volumes
    assert all(name.startswith(f"{identity.project_id}_") for name in marker_volume_ids.values())


async def test_empty_redis_tolerance_and_no_schema_actions(
    monotonic_clock: MonotonicClock,
    identity: Any,
    runtime_base: Path,
    manifest: Any,
) -> None:
    world = FakeDownWorld(monotonic_clock)
    world.seed_running(identity)
    outcome = await lifecycle_module.stop_local_environment(
        repo_root=Path("/sf02-persistence-repo"),
        identity=identity,
        manifest_loader=lambda: manifest,
        runtime_base=runtime_base,
        adapter_factory=world.factory,
        clock=monotonic_clock,
    )
    assert outcome.status == "PASSED"
    assert "redis-data" in world.volumes
    blob = "\n".join(outcome.plain_lines)
    for forbidden in ("alembic", "CREATE TABLE", "INSERT INTO", "seed", "migrate"):
        assert forbidden not in blob.lower()


def _docker_daemon_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    import subprocess

    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not _docker_daemon_ready(),
    reason="local Docker daemon required for real-Compose marker persistence",
)
async def test_real_compose_ten_cycles_retain_postgres_marker(
    real_compose_project_factory: RealComposeProjectFactory,
    network_probe_runner: NetworkProbeRunner,
) -> None:
    """T076: write a marker, cycle stop/start ten times, prove the row survives."""
    project = real_compose_project_factory.new()
    first = await real_compose_project_factory.start(project)
    assert first.status == "PASSED", first.message

    marker = "cycle_marker_v1"
    password = project.secrets_map["postgres"]
    write_script = (
        f"PGPASSWORD='{password}' psql -h postgres -p 5432 "
        f"-U {project.username} -d {project.database} -v ON_ERROR_STOP=1 "
        f"-c {postgres_marker_sql(marker)!r}\n"
    )
    # Use separate statements for CREATE/INSERT to keep quoting simple.
    write_script = (
        f"PGPASSWORD='{password}' psql -h postgres -p 5432 "
        f"-U {project.username} -d {project.database} -v ON_ERROR_STOP=1 <<'SQL'\n"
        "CREATE TABLE IF NOT EXISTS sf02_marker(id text PRIMARY KEY);\n"
        f"INSERT INTO sf02_marker(id) VALUES ('{marker}') ON CONFLICT DO NOTHING;\n"
        "SQL\n"
    )
    write = network_probe_runner._run_script(
        project,
        dependency=DependencyId.POSTGRES,
        script=write_script,
        secret=password,
        matcher=lambda _out: True,
    )
    assert write.exit_code == 0, write.stderr

    for cycle in range(10):
        down = await lifecycle_module.stop_local_environment(
            repo_root=real_compose_project_factory._repo_root,
            identity=project.identity,
            runtime_base=project.runtime_base,
            adapter_factory=real_compose_project_factory.adapter_factory(),
        )
        assert down.status == "PASSED", f"cycle {cycle} down: {down.message}"
        # Docker Desktop / WSL2 在 compose down 后可能短暂保留端口不可绑定状态
        # （例如 TIME_WAIT），必须等真实可 bind 后再验证持久化重启。
        for port in project.ports.values():
            _wait_port_free(port)
        up = await real_compose_project_factory.start(project)
        assert up.status == "PASSED", f"cycle {cycle} start: {up.message}"

    assert redis_reset_is_allowed()
    read = network_probe_runner._run_script(
        project,
        dependency=DependencyId.POSTGRES,
        script=(
            f"PGPASSWORD='{password}' psql -h postgres -p 5432 "
            f"-U {project.username} -d {project.database} -tAc "
            f"{postgres_marker_query_sql(marker)!r}\n"
        ),
        secret=password,
        matcher=lambda out: marker in out,
    )
    assert read.matched, f"marker not retained: stdout={read.stdout!r} stderr={read.stderr!r}"
