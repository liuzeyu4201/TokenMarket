"""Connection fact tests for host/container projections (T050, US3).

Host URLs from ``.env.local`` are the sole address/port facts; container
addresses replace only host/port with the canonical service names; safe
output never includes user-info; no competing port or container-URL fields
exist in configuration or public lifecycle messages.
"""

from __future__ import annotations

from workflow.local_env.config import parse_local_environment
from workflow.local_env.models import DependencyId


def _config_text(*, pg_port: int = 5432, redis_port: int = 6379, grafana_port: int = 3000) -> str:
    secret = "tm_local_" + ("a" * 32)
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://app:{secret}@127.0.0.1:{pg_port}/tokenmarket\n"
        f"REDIS_URL=redis://default:{secret}@127.0.0.1:{redis_port}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{grafana_port}\n"
        f"GRAFANA_ADMIN_PASSWORD={secret}\n"
    )


def test_host_urls_are_sole_port_facts() -> None:
    config = parse_local_environment(
        _config_text(pg_port=15432, redis_port=16379, grafana_port=13000)
    )
    assert config.connection(DependencyId.POSTGRES).host_port == 15432
    assert config.connection(DependencyId.REDIS).host_port == 16379
    assert config.connection(DependencyId.GRAFANA).host_port == 13000
    # No competing top-level port fields on the configuration object.
    assert not hasattr(config, "postgres_port")
    assert not hasattr(config, "redis_port")
    assert not hasattr(config, "grafana_port")
    assert not hasattr(config, "POSTGRES_PORT")


def test_container_urls_replace_only_host_and_port() -> None:
    secret = "tm_local_" + ("a" * 32)
    config = parse_local_environment(_config_text())
    postgres = config.connection(DependencyId.POSTGRES)
    redis = config.connection(DependencyId.REDIS)
    grafana = config.connection(DependencyId.GRAFANA)

    assert postgres.container_host == "postgres" and postgres.container_port == 5432
    assert redis.container_host == "redis" and redis.container_port == 6379
    assert grafana.container_host == "grafana" and grafana.container_port == 3000

    assert postgres.container_url == f"postgresql://app:{secret}@postgres:5432/tokenmarket"
    assert redis.container_url == f"redis://default:{secret}@redis:6379/0"
    assert grafana.container_url == "http://grafana:3000"


def test_safe_output_strips_user_info() -> None:
    config = parse_local_environment(_config_text())
    hosts = config.displayed_endpoints()
    containers = config.displayed_container_endpoints()

    assert hosts == {
        "postgres": "postgresql://127.0.0.1:5432/tokenmarket",
        "redis": "redis://127.0.0.1:6379/0",
        "grafana": "http://127.0.0.1:3000",
    }
    assert containers == {
        "postgres": "postgresql://postgres:5432/tokenmarket",
        "redis": "redis://redis:6379/0",
        "grafana": "http://grafana:3000",
    }
    blob = "\n".join([*hosts.values(), *containers.values()])
    assert "tm_local_" not in blob
    assert "@" not in blob
    assert "app" not in blob
    assert "default" not in blob


def test_no_competing_container_url_configuration_fields() -> None:
    config = parse_local_environment(_config_text())
    assert not hasattr(config, "DATABASE_CONTAINER_URL")
    assert not hasattr(config, "container_urls")
    # Credentials live only on the private DerivedConnection fields.
    postgres = config.connection(DependencyId.POSTGRES)
    assert "tm_local_" in postgres.container_url
    assert "tm_local_" not in repr(postgres)
