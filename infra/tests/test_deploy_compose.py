"""Structural tests for deploy middleware and merged deploy stack (ADR 003)."""

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
DOCKER_DIR = REPO_ROOT / "infra" / "docker"
MIDDLEWARE_FILE = DOCKER_DIR / "compose.middleware.yml"
DEPLOY_FILE = DOCKER_DIR / "compose.deploy.yml"
LOCAL_FILE = DOCKER_DIR / "compose.local.yml"
MANIFEST_FILE = REPO_ROOT / "ops" / "workflow" / "local-dependencies.json"

PROJECT_NAME = "tokenmarket-test"

MIDDLEWARE_SERVICES = ("postgres", "redis", "grafana")
APP_SERVICES = (
    "proxy-gateway",
    "api-service",
    "billing-service",
    "admin-service",
    "frontend",
)

CHILD_ENV = {
    "TOKENMARKET_DEPLOY_ENVIRONMENT": "test",
    "TOKENMARKET_DEPLOY_POSTGRES_USER": "deploy_user",
    "TOKENMARKET_DEPLOY_POSTGRES_DB": "tokenmarket",
    "TOKENMARKET_DEPLOY_POSTGRES_HOST_PORT": "15432",
    "TOKENMARKET_DEPLOY_REDIS_HOST_PORT": "16379",
    "TOKENMARKET_DEPLOY_GRAFANA_HOST_PORT": "13000",
    "TOKENMARKET_DEPLOY_POSTGRES_PASSWORD": "tm_local_" + "d" * 32,
    "TOKENMARKET_DEPLOY_REDIS_CONFIG": "requirepass " + "tm_local_" + "e" * 32,
    "TOKENMARKET_DEPLOY_GRAFANA_ADMIN_PASSWORD": "tm_local_" + "f" * 32,
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
        "postgresql://deploy_user:tm_local_" + "d" * 32 + "@postgres:5432/tokenmarket"
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
    "floating latest tag": re.compile(r":latest\b"),
    "docker socket mount": re.compile(r"docker\.sock"),
    "workspace local path leakage": re.compile(r"TOKENMARKET_WORKSPACE_"),
}


def _require_docker_compose() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI with the Compose plugin is required")


def _run_compose_config(*files: Path) -> dict[str, Any]:
    _require_docker_compose()
    env = dict(os.environ)
    env.update(CHILD_ENV)
    args = [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
    ]
    for path in files:
        args.extend(["-f", str(path)])
    args.extend(["config", "--format", "json"])
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(DOCKER_DIR),
    )
    assert result.returncode == 0, (
        f"docker compose config failed for {[p.name for p in files]}:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    model: dict[str, Any] = json.loads(result.stdout)
    return model


def _manifest_image(dep_id: str) -> str:
    data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    for item in data["dependencies"]:
        if item["id"] == dep_id:
            return f"{item['repository']}:{item['version_tag']}@{item['index_digest']}"
    raise AssertionError(f"dependency {dep_id} missing from manifest")


def test_middleware_and_deploy_files_exist() -> None:
    assert MIDDLEWARE_FILE.is_file()
    assert DEPLOY_FILE.is_file()
    assert LOCAL_FILE.is_file()


def test_deploy_include_references_sibling_files() -> None:
    text = DEPLOY_FILE.read_text(encoding="utf-8")
    assert "compose.middleware.yml" in text
    assert "compose.app.yml" in text
    assert "compose.local.yml" not in text


@pytest.mark.parametrize(
    "path",
    [MIDDLEWARE_FILE, DEPLOY_FILE],
    ids=["middleware", "deploy"],
)
def test_deploy_assets_forbid_raw_forms(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN_RAW_FORMS.items():
        assert not pattern.search(text), f"{path.name}: forbidden {label}"


def test_middleware_images_match_local_dependency_manifest() -> None:
    model = _run_compose_config(MIDDLEWARE_FILE)
    services = model["services"]
    assert set(services) == set(MIDDLEWARE_SERVICES)
    for dep_id in MIDDLEWARE_SERVICES:
        assert services[dep_id]["image"] == _manifest_image(dep_id)


def test_middleware_uses_deploy_labels_not_workspace_fingerprint() -> None:
    model = _run_compose_config(MIDDLEWARE_FILE)
    for name in MIDDLEWARE_SERVICES:
        labels = model["services"][name].get("labels") or {}
        assert labels.get("com.tokenmarket.environment") == "test"
        assert labels.get("com.tokenmarket.stack") == "deploy"
        assert "com.tokenmarket.workspace-id" not in labels
        assert "com.tokenmarket.workspace-fingerprint" not in labels


def test_middleware_ports_are_loopback() -> None:
    model = _run_compose_config(MIDDLEWARE_FILE)
    for name in MIDDLEWARE_SERVICES:
        for port in model["services"][name].get("ports") or []:
            assert port.get("host_ip") in ("127.0.0.1", "127.0.0.1/32")


def test_middleware_retains_named_volumes_for_postgres_and_redis() -> None:
    model = _run_compose_config(MIDDLEWARE_FILE)
    volumes = model.get("volumes") or {}
    # Compose may prefix project name; logical keys end with the declared names.
    keys = " ".join(volumes.keys())
    assert "postgres-data" in keys
    assert "redis-data" in keys


def test_merged_deploy_stack_has_middleware_and_apps() -> None:
    model = _run_compose_config(DEPLOY_FILE)
    services = set((model.get("services") or {}).keys())
    assert services == set(MIDDLEWARE_SERVICES) | set(APP_SERVICES)


def test_local_compose_still_excludes_application_services() -> None:
    text = LOCAL_FILE.read_text(encoding="utf-8")
    # Comments may mention out-of-scope names; forbid service definitions only.
    for service in APP_SERVICES:
        assert not re.search(
            rf"(?m)^\s*{re.escape(service)}\s*:",
            text,
        ), f"local compose must not define service {service}"
    assert "compose.app.yml" not in text
    assert "TOKENMARKET_DEPLOY_" not in text
