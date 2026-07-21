"""Structural contract tests for ``infra/docker/compose.local.yml`` (T020).

The SF02 lifecycle adapter feeds this exact file to the Compose CLI, so these
tests pin the reviewed model: exactly the three manifest dependencies with
immutable index-digest image references, canonical service DNS names, one
project-scoped default network, loopback-only long-syntax port publishers,
PostgreSQL/Redis named volumes, an explicit 0700 Grafana tmpfs, verified
non-root runtime users, environment-source 0400 secret files, authenticated
healthchecks, 60/30/30 stop grace periods, and the absence of forbidden
Compose forms.

Structure is validated through ``docker compose config --format json`` output
(the Compose CLI plugin only; no daemon resources are created) rendered with
a synthetic child environment, plus raw-text guards for forms the rendered
model cannot distinguish. Expectations derive from the committed runtime
manifest. No PyYAML and no real secret material is involved.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker" / "compose.local.yml"
MANIFEST_FILE = REPO_ROOT / "ops" / "workflow" / "local-dependencies.json"

PROJECT_ID = "tokenmarket-000000000000"
WORKSPACE_FINGERPRINT = "0" * 64

POSTGRES_HOST_PORT = "15432"
REDIS_HOST_PORT = "16379"
GRAFANA_HOST_PORT = "13000"
POSTGRES_USER = "sf02_user"
POSTGRES_DB = "sf02_db"
POSTGRES_PASSWORD = "tm_local_" + "a" * 32
REDIS_PASSWORD = "tm_local_" + "b" * 32
REDIS_CONFIG = "requirepass " + REDIS_PASSWORD
GRAFANA_ADMIN_PASSWORD = "tm_local_" + "c" * 32

SECRET_VALUES = (
    POSTGRES_PASSWORD,
    REDIS_PASSWORD,
    REDIS_CONFIG,
    GRAFANA_ADMIN_PASSWORD,
)

CHILD_ENV = {
    "TOKENMARKET_WORKSPACE_ID": PROJECT_ID,
    "TOKENMARKET_WORKSPACE_FINGERPRINT": WORKSPACE_FINGERPRINT,
    "TOKENMARKET_POSTGRES_HOST_PORT": POSTGRES_HOST_PORT,
    "TOKENMARKET_REDIS_HOST_PORT": REDIS_HOST_PORT,
    "TOKENMARKET_GRAFANA_HOST_PORT": GRAFANA_HOST_PORT,
    "TOKENMARKET_POSTGRES_USER": POSTGRES_USER,
    "TOKENMARKET_POSTGRES_DB": POSTGRES_DB,
    "TOKENMARKET_POSTGRES_PASSWORD": POSTGRES_PASSWORD,
    "TOKENMARKET_REDIS_CONFIG": REDIS_CONFIG,
    "TOKENMARKET_GRAFANA_ADMIN_PASSWORD": GRAFANA_ADMIN_PASSWORD,
}

EXPECTED_LABELS = {
    "com.tokenmarket.repository": "tokenmarket",
    "com.tokenmarket.workspace-id": PROJECT_ID,
    "com.tokenmarket.workspace-fingerprint": WORKSPACE_FINGERPRINT,
}

EXPECTED_PORTS = {
    "postgres": POSTGRES_HOST_PORT,
    "redis": REDIS_HOST_PORT,
    "grafana": GRAFANA_HOST_PORT,
}

EXPECTED_SECRET_SOURCES = {
    "postgres_password": "TOKENMARKET_POSTGRES_PASSWORD",
    "redis_config": "TOKENMARKET_REDIS_CONFIG",
    "grafana_admin_password": "TOKENMARKET_GRAFANA_ADMIN_PASSWORD",
}

EXPECTED_SECRET_MOUNTS = {
    "postgres": [("postgres_password", "/run/secrets/postgres_password")],
    "redis": [("redis_config", "/run/secrets/redis.conf")],
    "grafana": [("grafana_admin_password", "/run/secrets/grafana_admin_password")],
}

INTERPOLATION_RE = re.compile(r"\$\{([^}]*)\}")
INTERPOLATION_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")

ALLOWED_INTERPOLATIONS = frozenset(
    {
        "TOKENMARKET_WORKSPACE_ID",
        "TOKENMARKET_WORKSPACE_FINGERPRINT",
        "TOKENMARKET_POSTGRES_HOST_PORT",
        "TOKENMARKET_REDIS_HOST_PORT",
        "TOKENMARKET_GRAFANA_HOST_PORT",
        "TOKENMARKET_POSTGRES_USER",
        "TOKENMARKET_POSTGRES_DB",
    }
)

FORBIDDEN_RAW_FORMS = {
    "fixed container name": re.compile(r"container_name"),
    "host network mode": re.compile(r"network_mode"),
    "privileged container": re.compile(r"privileged"),
    "image build instruction": re.compile(r"^\s*build\s*:", re.MULTILINE),
    "service startup ordering": re.compile(r"depends_on"),
    "wildcard bind address": re.compile(r"0\.0\.0\.0"),
    "environment file directive": re.compile(r"env_file"),
    "ignored dotenv reference": re.compile(r"\.env\.local"),
    "floating latest tag": re.compile(r":latest\b"),
    "fixed resource name": re.compile(r"^\s*name\s*:", re.MULTILINE),
    "external resource": re.compile(r"^\s*external\s*:", re.MULTILINE),
    "docker socket mount": re.compile(r"docker\.sock"),
    "local secret value": re.compile(r"tm_local_"),
    "plaintext postgres password": re.compile(r"POSTGRES_PASSWORD:"),
    "plaintext grafana password": re.compile(r"GF_SECURITY_ADMIN_PASSWORD:"),
    "plaintext redis password variable": re.compile(r"REDIS_PASSWORD"),
}

FORBIDDEN_SERVICE_KEYS = (
    "container_name",
    "network_mode",
    "privileged",
    "build",
    "depends_on",
    "env_file",
)

_DURATION_RE = re.compile(r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?")


def _duration_seconds(value: str) -> float:
    match = _DURATION_RE.fullmatch(value)
    if match is None or all(group is None for group in match.groups()):
        raise AssertionError(f"unexpected duration format: {value!r}")
    minutes = float(match.group(1)) if match.group(1) else 0.0
    seconds = float(match.group(2)) if match.group(2) else 0.0
    return minutes * 60.0 + seconds


def _load_manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return data


MANIFEST = _load_manifest()
DEPENDENCIES: dict[str, dict[str, Any]] = {
    definition["id"]: definition for definition in MANIFEST["dependencies"]
}


def _image_ref(definition: dict[str, Any]) -> str:
    return f"{definition['repository']}:{definition['version_tag']}@{definition['index_digest']}"


def _require_docker_compose() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI with the Compose plugin is required")


def _run_compose_config(*extra_args: str) -> subprocess.CompletedProcess[str]:
    _require_docker_compose()
    env = dict(os.environ)
    env.update(CHILD_ENV)
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT_ID,
            "-f",
            str(COMPOSE_FILE),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture(scope="module")
def raw_compose_text() -> str:
    return COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_model() -> dict[str, Any]:
    result = _run_compose_config("config", "--format", "json")
    assert (
        result.returncode == 0
    ), f"docker compose config failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    model: dict[str, Any] = json.loads(result.stdout)
    return model


def test_compose_file_is_a_regular_file() -> None:
    assert COMPOSE_FILE.is_file(), f"missing {COMPOSE_FILE}"
    assert not COMPOSE_FILE.is_symlink()


def test_compose_file_uses_spaces_only(raw_compose_text: str) -> None:
    assert "\t" not in raw_compose_text


@pytest.mark.parametrize(
    "label,pattern",
    list(FORBIDDEN_RAW_FORMS.items()),
    ids=list(FORBIDDEN_RAW_FORMS),
)
def test_forbidden_raw_forms(
    raw_compose_text: str, label: str, pattern: re.Pattern[str]
) -> None:
    assert not pattern.search(
        raw_compose_text
    ), f"forbidden Compose form present: {label}"


def test_no_secret_material_enters_the_yaml(raw_compose_text: str) -> None:
    for value in SECRET_VALUES:
        assert value not in raw_compose_text
    for line in raw_compose_text.splitlines():
        if "requirepass" in line:
            assert (
                "sed -n 's/^requirepass //p'" in line
            ), "the Redis password directive may only appear in the healthcheck extractor"


def test_interpolations_are_strict_runtime_variables(raw_compose_text: str) -> None:
    names = INTERPOLATION_RE.findall(raw_compose_text)
    assert names, "expected runtime-injected interpolation variables"
    for name in names:
        assert INTERPOLATION_NAME_RE.fullmatch(
            name
        ), f"interpolation ${{{name}}} must not carry defaults, errors, or values"
    assert set(names) == ALLOWED_INTERPOLATIONS


def test_secret_environment_sources_are_named_in_raw_text(
    raw_compose_text: str,
) -> None:
    for variable in EXPECTED_SECRET_SOURCES.values():
        assert f"environment: {variable}" in raw_compose_text


def test_ports_use_long_syntax(raw_compose_text: str) -> None:
    in_ports = False
    ports_indent = 0
    entries = 0
    for line in raw_compose_text.splitlines():
        stripped = line.strip()
        if stripped == "ports:":
            in_ports = True
            ports_indent = len(line) - len(line.lstrip())
            continue
        if not in_ports or not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= ports_indent:
            in_ports = False
            continue
        if stripped.startswith("-"):
            entries += 1
            assert stripped.startswith(
                "- target:"
            ), f"port entries must use long syntax: {line!r}"
    assert entries == 3


def test_config_quiet_passes_with_synthetic_environment() -> None:
    result = _run_compose_config("config", "--quiet")
    assert result.returncode == 0, (
        f"docker compose config --quiet failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_exactly_the_three_canonical_services(compose_model: dict[str, Any]) -> None:
    assert set(compose_model["services"]) == {"postgres", "redis", "grafana"}


def test_images_match_the_reviewed_manifest_index_digests(
    compose_model: dict[str, Any]
) -> None:
    services = compose_model["services"]
    for dependency_id, definition in DEPENDENCIES.items():
        assert services[dependency_id]["image"] == _image_ref(definition)


def test_no_forbidden_service_keys(compose_model: dict[str, Any]) -> None:
    for service in compose_model["services"].values():
        for key in FORBIDDEN_SERVICE_KEYS:
            assert key not in service, f"forbidden service key present: {key}"


def test_ports_publish_loopback_only_from_injected_variables(
    compose_model: dict[str, Any],
) -> None:
    for dependency_id, definition in DEPENDENCIES.items():
        ports = compose_model["services"][dependency_id]["ports"]
        assert len(ports) == 1
        (entry,) = ports
        assert entry["host_ip"] == "127.0.0.1"
        assert entry["target"] == definition["container_port"]
        assert entry["published"] == EXPECTED_PORTS[dependency_id]
        assert entry["protocol"] == "tcp"
        assert entry["mode"] == "ingress"


def test_single_project_scoped_default_network(compose_model: dict[str, Any]) -> None:
    networks = compose_model["networks"]
    assert set(networks) == {"default"}
    default = networks["default"]
    assert default["name"] == f"{PROJECT_ID}_default"
    assert default["labels"] == EXPECTED_LABELS
    for service in compose_model["services"].values():
        assert set(service.get("networks", {"default": None})) == {"default"}


def test_named_volumes_are_project_scoped_and_labeled(
    compose_model: dict[str, Any]
) -> None:
    volumes = compose_model["volumes"]
    assert set(volumes) == {"postgres-data", "redis-data"}
    for logical_name, volume in volumes.items():
        assert volume["name"] == f"{PROJECT_ID}_{logical_name}"
        assert volume["labels"] == EXPECTED_LABELS


def test_postgres_and_redis_mount_their_named_volumes(
    compose_model: dict[str, Any]
) -> None:
    expectations = {
        "postgres": ("postgres-data", "/var/lib/postgresql/data"),
        "redis": ("redis-data", "/data"),
    }
    for dependency_id, (source, target) in expectations.items():
        mounts = compose_model["services"][dependency_id]["volumes"]
        actual = [(mount["type"], mount["source"], mount["target"]) for mount in mounts]
        assert actual == [("volume", source, target)]


def test_grafana_uses_only_the_0700_tmpfs(compose_model: dict[str, Any]) -> None:
    definition = DEPENDENCIES["grafana"]
    grafana = compose_model["services"]["grafana"]
    assert not grafana.get("volumes"), "Grafana must not declare any volume"
    expected_tmpfs = (
        f"{definition['ephemeral_storage']['mount_path']}:rw,"
        f"mode={definition['ephemeral_storage']['mode']},"
        f"uid={definition['runtime_uid']},gid={definition['runtime_gid']}"
    )
    assert grafana["tmpfs"] == [expected_tmpfs]


def test_services_run_as_the_verified_non_root_users(
    compose_model: dict[str, Any]
) -> None:
    for dependency_id, definition in DEPENDENCIES.items():
        service = compose_model["services"][dependency_id]
        assert definition["runtime_uid"] >= 1
        assert definition["runtime_gid"] >= 1
        assert (
            service["user"]
            == f"{definition['runtime_uid']}:{definition['runtime_gid']}"
        )


def test_services_carry_workspace_ownership_labels(
    compose_model: dict[str, Any]
) -> None:
    for service in compose_model["services"].values():
        assert service["labels"] == EXPECTED_LABELS


def test_top_level_secrets_use_environment_sources_only(
    compose_model: dict[str, Any]
) -> None:
    secrets = compose_model["secrets"]
    assert set(secrets) == set(EXPECTED_SECRET_SOURCES)
    for name, secret in secrets.items():
        assert secret["environment"] == EXPECTED_SECRET_SOURCES[name]
        assert "file" not in secret


def test_service_secret_mounts_are_0400_owned_files(
    compose_model: dict[str, Any]
) -> None:
    for dependency_id, mounts in EXPECTED_SECRET_MOUNTS.items():
        definition = DEPENDENCIES[dependency_id]
        entries = compose_model["services"][dependency_id]["secrets"]
        assert [(entry["source"], entry["target"]) for entry in entries] == mounts
        for entry in entries:
            assert entry["uid"] == str(definition["runtime_uid"])
            assert entry["gid"] == str(definition["runtime_gid"])
            assert entry["mode"] == "0400"


def _healthcheck_command(compose_model: dict[str, Any], dependency_id: str) -> str:
    test = compose_model["services"][dependency_id]["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL"
    command: str = test[1]
    return command


def _assert_short_healthcheck_timing(
    compose_model: dict[str, Any], dependency_id: str
) -> None:
    healthcheck = compose_model["services"][dependency_id]["healthcheck"]
    assert 0 < _duration_seconds(healthcheck["interval"]) <= 5.0
    assert 0 < _duration_seconds(healthcheck["timeout"]) <= 3.0
    assert healthcheck["retries"] >= 6
    assert "start_period" in healthcheck


def test_postgres_healthcheck_is_an_authenticated_select(
    compose_model: dict[str, Any]
) -> None:
    command = _healthcheck_command(compose_model, "postgres")
    assert "PGPASSWORD" in command
    assert "/run/secrets/postgres_password" in command
    assert "psql" in command
    assert "SELECT 1" in command
    assert "$$POSTGRES_USER" in command
    assert "$$POSTGRES_DB" in command
    assert "pg_isready" not in command
    assert POSTGRES_PASSWORD not in command
    _assert_short_healthcheck_timing(compose_model, "postgres")


def test_redis_healthcheck_authenticates_without_argv_password(
    compose_model: dict[str, Any],
) -> None:
    command = _healthcheck_command(compose_model, "redis")
    assert "REDISCLI_AUTH" in command
    assert "redis-cli" in command
    assert "PING" in command
    assert "/run/secrets/redis.conf" in command
    assert " -a " not in command
    assert REDIS_PASSWORD not in command
    _assert_short_healthcheck_timing(compose_model, "redis")


def test_grafana_healthcheck_covers_database_and_admin_identity(
    compose_model: dict[str, Any],
) -> None:
    command = _healthcheck_command(compose_model, "grafana")
    assert "/api/health" in command
    assert '"database":"ok"' in command
    assert "/api/user" in command
    assert '"isGrafanaAdmin":true' in command
    assert "Authorization: Basic" in command
    assert "/run/secrets/grafana_admin_password" in command
    assert GRAFANA_ADMIN_PASSWORD not in command
    _assert_short_healthcheck_timing(compose_model, "grafana")


def test_stop_grace_periods_match_the_manifest(compose_model: dict[str, Any]) -> None:
    for dependency_id, definition in DEPENDENCIES.items():
        grace = compose_model["services"][dependency_id]["stop_grace_period"]
        assert _duration_seconds(grace) == float(
            definition["stop_grace_period_seconds"]
        )


def test_postgres_environment_wires_the_password_file(
    compose_model: dict[str, Any]
) -> None:
    environment = compose_model["services"]["postgres"]["environment"]
    assert environment["POSTGRES_USER"] == POSTGRES_USER
    assert environment["POSTGRES_DB"] == POSTGRES_DB
    assert environment["POSTGRES_PASSWORD_FILE"] == "/run/secrets/postgres_password"
    assert "POSTGRES_PASSWORD" not in environment


def test_grafana_environment_wires_the_password_file(
    compose_model: dict[str, Any]
) -> None:
    environment = compose_model["services"]["grafana"]["environment"]
    assert environment["GF_SECURITY_ADMIN_USER"] == "admin"
    assert (
        environment["GF_SECURITY_ADMIN_PASSWORD__FILE"]
        == "/run/secrets/grafana_admin_password"
    )
    assert "GF_SECURITY_ADMIN_PASSWORD" not in environment


def test_redis_command_loads_only_the_secret_config_file(
    compose_model: dict[str, Any]
) -> None:
    command = compose_model["services"]["redis"].get("command")
    assert command == ["redis-server", "/run/secrets/redis.conf"]


def test_no_secret_value_appears_anywhere_in_the_rendered_model(
    compose_model: dict[str, Any],
) -> None:
    rendered = json.dumps(compose_model)
    assert "tm_local_" not in rendered
    for value in SECRET_VALUES:
        assert value not in rendered
