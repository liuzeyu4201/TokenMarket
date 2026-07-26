"""Local HTTPS frontend /api proxy structural tests (004 T014 partial).

Asserts Vite HTTPS plugin + same-origin `/api` proxy, exact basic-ssl pin, and
that compose.local.yml remains middleware-only (no business services).
"""

from __future__ import annotations

import json
import re

from .helpers import load_text, repo_path


def _vite_config() -> str:
    return load_text("frontend", "vite.config.ts")


def _package_json() -> dict:
    return json.loads(load_text("frontend", "package.json"))


def _compose_local() -> str:
    return load_text("infra", "docker", "compose.local.yml")


def test_vite_config_enables_basic_ssl_https_plugin() -> None:
    src = _vite_config()
    assert "plugin-basic-ssl" in src or "@vitejs/plugin-basic-ssl" in src
    assert "basicSsl" in src
    assert re.search(r"https\s*:\s*true", src), "vite server.https must be true"
    assert "127.0.0.1" in src
    assert "5173" in src


def test_vite_config_proxies_api_to_loopback_api_service() -> None:
    src = _vite_config()
    assert "'/api'" in src or '"/api"' in src
    assert "proxy" in src
    assert "changeOrigin" in src
    assert "127.0.0.1:8000" in src or "VITE_API_PROXY_TARGET" in src
    # secure: false is required when proxying HTTPS origin → HTTP API
    assert re.search(r"secure\s*:\s*false", src)


def test_package_json_pins_basic_ssl_2_3_0() -> None:
    pkg = _package_json()
    dev = pkg.get("devDependencies") or {}
    assert "@vitejs/plugin-basic-ssl" in dev
    raw = str(dev["@vitejs/plugin-basic-ssl"]).lstrip("^~=")
    assert raw == "2.3.0", f"expected @vitejs/plugin-basic-ssl@2.3.0, got {dev['@vitejs/plugin-basic-ssl']!r}"
    runtime = pkg.get("dependencies") or {}
    assert "@vitejs/plugin-basic-ssl" not in runtime


def test_compose_local_excludes_business_services() -> None:
    """SF02 compose.local.yml is middleware only — never api/frontend/gateway images."""
    text = _compose_local()
    # Named middleware services that are allowed
    assert re.search(r"(?m)^\s*postgres\s*:", text)
    assert re.search(r"(?m)^\s*redis\s*:", text)
    assert re.search(r"(?m)^\s*grafana\s*:", text)

    for service in (
        "api-service",
        "billing-service",
        "admin-service",
        "proxy-gateway",
        "frontend",
    ):
        assert not re.search(rf"(?m)^\s*{re.escape(service)}\s*:", text), (
            f"compose.local.yml must not define business service {service}"
        )

    for marker in (
        "TOKENMARKET_DEPLOY_IMAGE_FRONTEND",
        "tokenmarket/frontend",
        "tokenmarket/api-service",
    ):
        assert marker not in text, f"unexpected business image marker {marker}"


def test_compose_local_file_exists_at_canonical_path() -> None:
    path = repo_path("infra", "docker", "compose.local.yml")
    assert path.is_file()


def test_local_stack_five_host_processes_defined() -> None:
    """make start manages five host application processes (T131)."""
    src = load_text("tools", "workflow", "local_stack", "processes.py")
    assert "five application processes" in src or "five" in src.lower()
    for service_id in (
        "proxy-gateway",
        "api-service",
        "billing-service",
        "admin-service",
        "frontend",
    ):
        assert f'id="{service_id}"' in src or f"id='{service_id}'" in src


def test_local_stack_does_not_inject_direct_api_base_url() -> None:
    """FR-012a: frontend must use relative /api via Vite proxy (T125)."""
    src = load_text("tools", "workflow", "local_stack", "processes.py")
    assert "VITE_API_PROXY_TARGET" in src
    # Must not force browser at API host
    assert 'VITE_API_BASE_URL": f"http://127.0.0.1:{ports.api}"' not in src
    assert "VITE_API_BASE_URL" in src  # cleared to empty string
    assert 'VITE_API_BASE_URL": ""' in src or "VITE_API_BASE_URL': ''" in src


def test_local_stack_api_dispatcher_lifecycle_env_hook() -> None:
    """Dispatcher can be enabled via AUTH_DISPATCHER_* on API process env."""
    # compose.app carries deploy dispatcher flags; local stack inherits AUTH_* from .env.local
    app_compose = load_text("infra", "docker", "compose.app.yml")
    assert "AUTH_DISPATCHER_ENABLED" in app_compose
    assert "AUTH_DISPATCHER_LEASE_SECONDS" in app_compose


def test_vite_https_self_signed_probe_contract() -> None:
    """Restricted self-signed HTTPS probe: basic-ssl + https true + loopback host."""
    src = _vite_config()
    assert re.search(r"https\s*:\s*true", src)
    assert "basicSsl" in src
    assert "127.0.0.1" in src
