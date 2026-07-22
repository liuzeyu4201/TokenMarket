"""Project-network connectivity integration tests (T051/T078, US3).

Executes authenticated PostgreSQL ``SELECT 1``, Redis AUTH/PING, and Grafana
health/admin HTTP checks via :class:`NetworkProbeRunner` against a disposable
real Compose project. Skips when Docker is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from .conftest import NetworkProbeRunner, RealComposeProjectFactory


def _docker_daemon_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_daemon_ready(),
    reason="local Docker daemon required for project-network connectivity probes",
)


async def test_project_network_probes_execute_real_protocols(
    real_compose_project_factory: RealComposeProjectFactory,
    network_probe_runner: NetworkProbeRunner,
) -> None:
    project = real_compose_project_factory.new()
    outcome = await real_compose_project_factory.start(project)
    assert outcome.status == "PASSED", outcome.message

    postgres = network_probe_runner.probe_postgres(project)
    redis = network_probe_runner.probe_redis(project)
    grafana = network_probe_runner.probe_grafana(project)

    assert postgres.matched and postgres.exit_code == 0
    assert redis.matched and redis.exit_code == 0
    assert grafana.matched and grafana.exit_code == 0
    # Evidence must remain secret-free.
    for evidence in (postgres, redis, grafana):
        for secret in project.secrets_map.values():
            assert secret not in evidence.stdout
            assert secret not in evidence.stderr
