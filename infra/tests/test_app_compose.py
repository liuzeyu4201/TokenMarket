"""Structural contract tests for ``infra/docker/compose.app.yml`` (ADR 003).

Layer A defines exactly five application services as pre-built images with
loopback publishers, deploy labels, and no build contexts or forbidden forms.
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
COMPOSE_FILE = REPO_ROOT / "infra" / "docker" / "compose.app.yml"

EXPECTED_SERVICES = (
    "proxy-gateway",
    "api-service",
    "billing-service",
    "admin-service",
    "frontend",
)

CHILD_ENV = {
    "TOKENMARKET_DEPLOY_ENVIRONMENT": "test",
    "TOKENMARKET_DEPLOY_IMAGE_PROXY_GATEWAY": "tokenmarket/proxy-gateway:0.1.0",
    "TOKENMARKET_DEPLOY_IMAGE_API_SERVICE": "tokenmarket/api-service:0.1.0",
    "TOKENMARKET_DEPLOY_IMAGE_BILLING_SERVICE": "tokenmarket/billing-service:0.1.0",
    "TOKENMARKET_DEPLOY_IMAGE_ADMIN_SERVICE": "tokenmarket/admin-service:0.1.0",
    "TOKENMARKET_DEPLOY_IMAGE_FRONTEND": "tokenmarket/frontend:0.1.0",
    "TOKENMARKET_DEPLOY_GATEWAY_HOST_PORT": "18080",
    "TOKENMARKET_DEPLOY_API_HOST_PORT": "18000",
    "TOKENMARKET_DEPLOY_BILLING_HOST_PORT": "18001",
    "TOKENMARKET_DEPLOY_ADMIN_HOST_PORT": "18002",
    "TOKENMARKET_DEPLOY_FRONTEND_HOST_PORT": "13080",
    "TOKENMARKET_DEPLOY_APP_DATABASE_URL": (
        "postgresql://app:tm_local_placeholder_not_a_real_secret_xxxx"
        "@postgres:5432/tokenmarket"
    ),
}

FORBIDDEN_RAW_FORMS = {
    "fixed container name": re.compile(r"container_name"),
    "host network mode": re.compile(r"network_mode"),
    "privileged container": re.compile(r"privileged"),
    "image build instruction": re.compile(r"^\s*build\s*:", re.MULTILINE),
    "service startup ordering": re.compile(r"depends_on"),
    "wildcard bind address": re.compile(r"0\.0\.0\.0"),
    "environment file directive": re.compile(r"env_file"),
    "ignored dotenv reference": re.compile(r"\.env\.(local|test|prod)"),
    "floating latest tag": re.compile(r":latest\b"),
    "docker socket mount": re.compile(r"docker\.sock"),
    "local compose path": re.compile(r"compose\.local\.yml"),
}

INTERPOLATION_RE = re.compile(r"\$\{([^}]*)\}")
INTERPOLATION_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


def _require_docker_compose() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI with the Compose plugin is required")


def _run_compose_config() -> subprocess.CompletedProcess[str]:
    _require_docker_compose()
    env = dict(os.environ)
    env.update(CHILD_ENV)
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "tokenmarket-test",
            "-f",
            str(COMPOSE_FILE),
            "config",
            "--format",
            "json",
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
    result = _run_compose_config()
    assert result.returncode == 0, (
        f"docker compose config failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    model: dict[str, Any] = json.loads(result.stdout)
    return model


def test_compose_app_file_exists() -> None:
    assert COMPOSE_FILE.is_file()
    assert not COMPOSE_FILE.is_symlink()


@pytest.mark.parametrize(
    "label,pattern", list(FORBIDDEN_RAW_FORMS.items()), ids=list(FORBIDDEN_RAW_FORMS)
)
def test_app_forbidden_raw_forms(
    raw_compose_text: str, label: str, pattern: re.Pattern[str]
) -> None:
    assert not pattern.search(raw_compose_text), f"forbidden form: {label}"


def test_interpolations_are_strict_names(raw_compose_text: str) -> None:
    names = INTERPOLATION_RE.findall(raw_compose_text)
    assert names
    for name in names:
        assert INTERPOLATION_NAME_RE.fullmatch(name), name
        assert name.startswith("TOKENMARKET_DEPLOY_"), name


def test_exactly_five_application_services(compose_model: dict[str, Any]) -> None:
    services = compose_model.get("services") or {}
    assert set(services) == set(EXPECTED_SERVICES)


@pytest.mark.parametrize("service", EXPECTED_SERVICES)
def test_service_uses_image_not_build(
    compose_model: dict[str, Any], service: str
) -> None:
    svc = compose_model["services"][service]
    assert "image" in svc
    assert "build" not in svc
    assert svc["image"].startswith("tokenmarket/")


@pytest.mark.parametrize("service", EXPECTED_SERVICES)
def test_service_publishes_loopback_only(
    compose_model: dict[str, Any], service: str
) -> None:
    ports = compose_model["services"][service].get("ports") or []
    assert ports, f"{service} must publish a host port"
    for port in ports:
        assert port.get("host_ip") in ("127.0.0.1", "127.0.0.1/32")


@pytest.mark.parametrize("service", EXPECTED_SERVICES)
def test_service_carries_deploy_labels(
    compose_model: dict[str, Any], service: str
) -> None:
    labels = compose_model["services"][service].get("labels") or {}
    assert labels.get("com.tokenmarket.repository") == "tokenmarket"
    assert labels.get("com.tokenmarket.environment") == "test"
    assert labels.get("com.tokenmarket.stack") == "deploy"
