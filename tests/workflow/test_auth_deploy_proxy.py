"""Deploy same-origin /api proxy and security header tests (004 T014 partial).

Asserts frontend/nginx.conf reverse-proxies `/api` to api-service with security
headers, and that compose.app.yml retains the frontend/api deploy surface with
documented auth/dispatcher configuration keys (hooks land with full T024).
"""

from __future__ import annotations

import re

from .helpers import load_text, repo_path

REQUIRED_SECURITY_HEADERS = (
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
)

# Expected auth process / dispatcher configuration keys (from .env.example).
# Full dispatcher lifecycle wiring is later T024 work; this documents the contract.
EXPECTED_AUTH_CONFIG_KEYS = (
    "AUTH_DISPATCHER_LEASE_SECONDS",
    "AUTH_DISPATCHER_DRAIN_SECONDS",
    "AUTH_BROWSER_ORIGINS",
    "AUTH_TRUSTED_PROXY_CIDRS",
    "AUTH_SMS_ADAPTER",
)


def _nginx_conf() -> str:
    return load_text("frontend", "nginx.conf")


def _compose_app() -> str:
    return load_text("infra", "docker", "compose.app.yml")


def _env_example() -> str:
    return load_text(".env.example")


def test_nginx_proxies_api_to_api_service() -> None:
    conf = _nginx_conf()
    assert re.search(r"location\s+/api/", conf), "nginx must define location /api/"
    assert "proxy_pass" in conf
    assert "api-service" in conf
    assert "8000" in conf


def test_nginx_security_headers_present() -> None:
    conf = _nginx_conf()
    for header in REQUIRED_SECURITY_HEADERS:
        assert header in conf, f"missing security header {header}"
    assert "nosniff" in conf
    assert "DENY" in conf
    assert "Cache-Control" in conf
    assert "no-cache" in conf


def test_nginx_keeps_spa_try_files_and_health() -> None:
    conf = _nginx_conf()
    assert "try_files" in conf
    assert "/health/live" in conf
    assert "listen 3000" in conf


def test_compose_app_includes_api_and_frontend_services() -> None:
    text = _compose_app()
    assert re.search(r"(?m)^\s*api-service\s*:", text)
    assert re.search(r"(?m)^\s*frontend\s*:", text)
    assert re.search(r"(?m)^\s*proxy-gateway\s*:", text)


def test_compose_app_or_env_documents_dispatcher_auth_hooks() -> None:
    """Dispatcher lifecycle env keys must be documented; compose may wire them later.

    Full T024 will inject AUTH_DISPATCHER_* into api-service environment and
    process managers. Until then, `.env.example` is the configuration contract.
    """
    env = _env_example()
    compose = _compose_app()
    combined = env + "\n" + compose
    missing = [k for k in EXPECTED_AUTH_CONFIG_KEYS if k not in combined]
    assert not missing, (
        "auth/dispatcher configuration keys must appear in .env.example "
        f"(and later compose.app.yml hooks): missing {missing}"
    )


def test_deploy_proxy_assets_exist() -> None:
    assert repo_path("frontend", "nginx.conf").is_file()
    assert repo_path("infra", "docker", "compose.app.yml").is_file()
