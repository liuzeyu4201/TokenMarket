"""Minimal deploy-stack lifecycle for ``make deploy`` / ``make deploy-down``.

Implements ADR 003 Layer D: merge middleware + app Compose files under a
fixed environment project name, inject child-only env, never delete volumes
on ordinary down. Secrets are read from ignored ``.env.test`` / ``.env.prod``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..mode import ModeError, ModeSelection, require_production_approval, validate_mode

DOCKER_DIR = Path("infra") / "docker"
COMPOSE_DEPLOY = DOCKER_DIR / "compose.deploy.yml"
CONFIG_FILES = {
    "test": ".env.test",
    "prod": ".env.prod",
}
PROJECT_NAMES = {
    "test": "tokenmarket-test",
    "prod": "tokenmarket-prod",
}

_SECRET_RE = re.compile(r"^tm_local_[A-Za-z0-9_-]{32,96}$")
_APP_IMAGES = (
    "IMAGE_PROXY_GATEWAY",
    "IMAGE_API_SERVICE",
    "IMAGE_BILLING_SERVICE",
    "IMAGE_ADMIN_SERVICE",
    "IMAGE_FRONTEND",
)


class DeployError(Exception):
    """Deploy lifecycle failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DeployConfig:
    mode: str
    project_name: str
    child_env: dict[str, str]
    app_images: tuple[str, ...]


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise DeployError(
            "INVALID_CONFIG",
            f"missing deploy config file {path.name}; copy placeholders from .env.example",
        )
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _require(cfg: dict[str, str], key: str) -> str:
    value = cfg.get(key, "").strip()
    if not value or value.startswith("replace-me"):
        raise DeployError(
            "INVALID_CONFIG",
            f"deploy config field {key} is missing or still a placeholder",
        )
    return value


def _require_secret(cfg: dict[str, str], key: str) -> str:
    value = _require(cfg, key)
    if not _SECRET_RE.fullmatch(value):
        raise DeployError(
            "INVALID_CONFIG",
            f"deploy config field {key} must match tm_local_ synthetic secret grammar",
        )
    return value


def load_deploy_config(repo_root: Path, selection: ModeSelection) -> DeployConfig:
    if selection.mode not in ("test", "prod"):
        raise DeployError(
            "INVALID_MODE",
            "make deploy requires mode=test or mode=prod on the Make command line",
        )
    path = repo_root / CONFIG_FILES[selection.mode]
    raw = _parse_dotenv(path)

    user = raw.get("POSTGRES_USER") or "tm_deploy"
    db = raw.get("POSTGRES_DB") or "tokenmarket"
    password = _require_secret(raw, "POSTGRES_PASSWORD")
    redis_password = _require_secret(raw, "REDIS_PASSWORD")
    grafana_password = _require_secret(raw, "GRAFANA_ADMIN_PASSWORD")

    def port(key: str, default: str) -> str:
        return raw.get(key, default).strip() or default

    images = {
        "TOKENMARKET_DEPLOY_IMAGE_PROXY_GATEWAY": raw.get(
            "IMAGE_PROXY_GATEWAY", "tokenmarket/proxy-gateway:0.1.0"
        ),
        "TOKENMARKET_DEPLOY_IMAGE_API_SERVICE": raw.get(
            "IMAGE_API_SERVICE", "tokenmarket/api-service:0.1.0"
        ),
        "TOKENMARKET_DEPLOY_IMAGE_BILLING_SERVICE": raw.get(
            "IMAGE_BILLING_SERVICE", "tokenmarket/billing-service:0.1.0"
        ),
        "TOKENMARKET_DEPLOY_IMAGE_ADMIN_SERVICE": raw.get(
            "IMAGE_ADMIN_SERVICE", "tokenmarket/admin-service:0.1.0"
        ),
        "TOKENMARKET_DEPLOY_IMAGE_FRONTEND": raw.get(
            "IMAGE_FRONTEND", "tokenmarket/frontend:0.1.0"
        ),
    }
    for key, image in images.items():
        if not image or ":latest" in image:
            raise DeployError("INVALID_CONFIG", f"invalid image reference for {key}")

    # App containers reach middleware by Compose DNS name `postgres`.
    app_database_url = (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@postgres:5432/{db}"
    )

    child_env = {
        **os.environ,
        "TOKENMARKET_DEPLOY_ENVIRONMENT": selection.mode,
        "TOKENMARKET_DEPLOY_POSTGRES_USER": user,
        "TOKENMARKET_DEPLOY_POSTGRES_DB": db,
        "TOKENMARKET_DEPLOY_POSTGRES_PASSWORD": password,
        "TOKENMARKET_DEPLOY_REDIS_CONFIG": f"requirepass {redis_password}",
        "TOKENMARKET_DEPLOY_GRAFANA_ADMIN_PASSWORD": grafana_password,
        "TOKENMARKET_DEPLOY_POSTGRES_HOST_PORT": port("POSTGRES_HOST_PORT", "5432"),
        "TOKENMARKET_DEPLOY_REDIS_HOST_PORT": port("REDIS_HOST_PORT", "6379"),
        "TOKENMARKET_DEPLOY_GRAFANA_HOST_PORT": port("GRAFANA_HOST_PORT", "3000"),
        "TOKENMARKET_DEPLOY_GATEWAY_HOST_PORT": port("GATEWAY_HOST_PORT", "8080"),
        "TOKENMARKET_DEPLOY_API_HOST_PORT": port("API_HOST_PORT", "8000"),
        "TOKENMARKET_DEPLOY_BILLING_HOST_PORT": port("BILLING_HOST_PORT", "8001"),
        "TOKENMARKET_DEPLOY_ADMIN_HOST_PORT": port("ADMIN_HOST_PORT", "8002"),
        "TOKENMARKET_DEPLOY_FRONTEND_HOST_PORT": port("FRONTEND_HOST_PORT", "3080"),
        "TOKENMARKET_DEPLOY_APP_DATABASE_URL": app_database_url,
        **images,
    }
    return DeployConfig(
        mode=selection.mode,
        project_name=PROJECT_NAMES[selection.mode],
        child_env=child_env,
        app_images=tuple(images.values()),
    )


def _compose_cmd(repo_root: Path, project: str, *args: str) -> list[str]:
    compose_file = repo_root / COMPOSE_DEPLOY
    if not compose_file.is_file():
        raise DeployError("CONTRACT_DRIFT", f"missing {COMPOSE_DEPLOY}")
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(compose_file),
        *args,
    ]


def _run(
    cmd: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _ensure_docker() -> None:
    if shutil.which("docker") is None:
        raise DeployError("TOOL_MISSING", "docker CLI is not installed")
    probe = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if probe.returncode != 0:
        raise DeployError("TOOL_MISSING", "docker daemon is not available")


def _ensure_app_images(images: tuple[str, ...]) -> None:
    missing: list[str] = []
    for image in images:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            missing.append(image)
    if missing:
        raise DeployError(
            "IMAGE_UNAVAILABLE",
            "missing app images (run make build first): " + ", ".join(missing),
        )


def _pull_middleware(env: dict[str, str], repo_root: Path, project: str) -> None:
    # Pull only middleware images declared in compose (app images are local).
    cmd = _compose_cmd(repo_root, project, "pull", "postgres", "redis", "grafana")
    result = _run(cmd, env=env, cwd=repo_root / DOCKER_DIR, timeout=600)
    if result.returncode != 0:
        # Non-fatal if already present; compose up will fail clearly otherwise.
        pass


def deploy_up(
    repo_root: Path,
    *,
    mode: str | None,
    mode_origin: str,
    plain: bool = False,
) -> int:
    """Reconcile the deploy stack and wait briefly for health."""
    try:
        selection = validate_mode(mode, mode_origin)
        if selection.mode == "local" or mode is None or mode == "":
            raise DeployError(
                "INVALID_MODE",
                "make deploy requires explicit mode=test or mode=prod",
            )
        if selection.mode == "prod":
            selection = require_production_approval(selection)
        _ensure_docker()
        cfg = load_deploy_config(repo_root, selection)
        _ensure_app_images(cfg.app_images)
        _print(plain, f"[STARTED] deploy project={cfg.project_name} mode={cfg.mode}")
        _pull_middleware(cfg.child_env, repo_root, cfg.project_name)
        up = _run(
            _compose_cmd(
                repo_root,
                cfg.project_name,
                "up",
                "-d",
                "--remove-orphans",
                "--pull",
                "missing",
            ),
            env=cfg.child_env,
            cwd=repo_root / DOCKER_DIR,
            timeout=600,
        )
        if up.returncode != 0:
            detail = (up.stderr or up.stdout or "").strip().splitlines()
            safe = detail[-1] if detail else "compose up failed"
            # Redact anything that looks like a password fragment.
            safe = re.sub(r"tm_local_[A-Za-z0-9_-]+", "[REDACTED]", safe)
            raise DeployError("STEP_FAILED", f"compose up failed: {safe[:200]}")

        # Bounded readiness: wait for compose health or container running.
        deadline = time.monotonic() + 90
        last = ""
        while time.monotonic() < deadline:
            ps = _run(
                _compose_cmd(repo_root, cfg.project_name, "ps", "--format", "json"),
                env=cfg.child_env,
                cwd=repo_root / DOCKER_DIR,
                timeout=60,
            )
            last = (ps.stdout or "")[:500]
            # Prefer healthy when available; accept running for services without health.
            if ps.returncode == 0 and "running" in (ps.stdout or "").lower():
                # Count services roughly.
                if (ps.stdout or "").count('"Name"') >= 8 or (ps.stdout or "").count(
                    "tokenmarket"
                ) >= 5:
                    # Probe a few loopback endpoints.
                    if _host_probes_ok(cfg):
                        _print(
                            plain,
                            f"[PASSED] deploy project={cfg.project_name} "
                            f"gateway=127.0.0.1:{cfg.child_env['TOKENMARKET_DEPLOY_GATEWAY_HOST_PORT']} "
                            f"frontend=127.0.0.1:{cfg.child_env['TOKENMARKET_DEPLOY_FRONTEND_HOST_PORT']}",
                        )
                        return 0
            time.sleep(3)

        raise DeployError(
            "DEPENDENCY_NOT_READY",
            "deploy stack did not become ready within 90s; inspect with "
            f"docker compose -p {cfg.project_name} ps",
        )
    except ModeError as exc:
        _print(plain, f"[FAILED] deploy [{exc.code}] {exc.message}")
        return 1
    except DeployError as exc:
        _print(plain, f"[FAILED] deploy [{exc.code}] {exc.message}")
        return 1
    except subprocess.TimeoutExpired:
        _print(plain, "[FAILED] deploy [STEP_FAILED] deploy command timed out")
        return 1


def deploy_down(
    repo_root: Path,
    *,
    mode: str | None,
    mode_origin: str,
    plain: bool = False,
) -> int:
    """Stop deploy stack containers without deleting named volumes."""
    try:
        selection = validate_mode(mode, mode_origin)
        if selection.mode not in ("test", "prod"):
            raise DeployError(
                "INVALID_MODE",
                "make deploy-down requires explicit mode=test or mode=prod",
            )
        if selection.mode == "prod":
            selection = require_production_approval(selection)
        _ensure_docker()
        # Down must work even if config secrets are missing: use placeholders.
        project = PROJECT_NAMES[selection.mode]
        placeholder_env = {
            **os.environ,
            "TOKENMARKET_DEPLOY_ENVIRONMENT": selection.mode,
            "TOKENMARKET_DEPLOY_POSTGRES_USER": "placeholder",
            "TOKENMARKET_DEPLOY_POSTGRES_DB": "placeholder",
            "TOKENMARKET_DEPLOY_POSTGRES_PASSWORD": "tm_local_" + "x" * 32,
            "TOKENMARKET_DEPLOY_REDIS_CONFIG": "requirepass " + "tm_local_" + "y" * 32,
            "TOKENMARKET_DEPLOY_GRAFANA_ADMIN_PASSWORD": "tm_local_" + "z" * 32,
            "TOKENMARKET_DEPLOY_POSTGRES_HOST_PORT": "5432",
            "TOKENMARKET_DEPLOY_REDIS_HOST_PORT": "6379",
            "TOKENMARKET_DEPLOY_GRAFANA_HOST_PORT": "3000",
            "TOKENMARKET_DEPLOY_GATEWAY_HOST_PORT": "8080",
            "TOKENMARKET_DEPLOY_API_HOST_PORT": "8000",
            "TOKENMARKET_DEPLOY_BILLING_HOST_PORT": "8001",
            "TOKENMARKET_DEPLOY_ADMIN_HOST_PORT": "8002",
            "TOKENMARKET_DEPLOY_FRONTEND_HOST_PORT": "3080",
            "TOKENMARKET_DEPLOY_APP_DATABASE_URL": "postgresql://u:p@postgres:5432/db",
            "TOKENMARKET_DEPLOY_IMAGE_PROXY_GATEWAY": "tokenmarket/proxy-gateway:0.1.0",
            "TOKENMARKET_DEPLOY_IMAGE_API_SERVICE": "tokenmarket/api-service:0.1.0",
            "TOKENMARKET_DEPLOY_IMAGE_BILLING_SERVICE": "tokenmarket/billing-service:0.1.0",
            "TOKENMARKET_DEPLOY_IMAGE_ADMIN_SERVICE": "tokenmarket/admin-service:0.1.0",
            "TOKENMARKET_DEPLOY_IMAGE_FRONTEND": "tokenmarket/frontend:0.1.0",
        }
        # Prefer real config when present so project labels match.
        try:
            cfg = load_deploy_config(repo_root, selection)
            env = cfg.child_env
            project = cfg.project_name
        except DeployError:
            env = placeholder_env

        down = _run(
            _compose_cmd(
                repo_root,
                project,
                "down",
                "--remove-orphans",
            ),
            env=env,
            cwd=repo_root / DOCKER_DIR,
            timeout=120,
        )
        if down.returncode != 0:
            safe = (down.stderr or down.stdout or "compose down failed")[:200]
            safe = re.sub(r"tm_local_[A-Za-z0-9_-]+", "[REDACTED]", safe)
            raise DeployError("STEP_FAILED", f"compose down failed: {safe}")
        _print(plain, f"[PASSED] deploy-down project={project} volumes retained")
        return 0
    except ModeError as exc:
        _print(plain, f"[FAILED] deploy-down [{exc.code}] {exc.message}")
        return 1
    except DeployError as exc:
        _print(plain, f"[FAILED] deploy-down [{exc.code}] {exc.message}")
        return 1
    except subprocess.TimeoutExpired:
        _print(plain, "[FAILED] deploy-down [STEP_FAILED] command timed out")
        return 1


def _host_probes_ok(cfg: DeployConfig) -> bool:
    import urllib.error
    import urllib.request

    # Host loopback probes must ignore HTTP(S)_PROXY (common on developer machines).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = [
        (
            "gateway",
            f"http://127.0.0.1:{cfg.child_env['TOKENMARKET_DEPLOY_GATEWAY_HOST_PORT']}/health/live",
        ),
        (
            "api",
            f"http://127.0.0.1:{cfg.child_env['TOKENMARKET_DEPLOY_API_HOST_PORT']}/health/live",
        ),
        (
            "frontend",
            f"http://127.0.0.1:{cfg.child_env['TOKENMARKET_DEPLOY_FRONTEND_HOST_PORT']}/health/live",
        ),
    ]
    ok = 0
    for _name, url in checks:
        try:
            with opener.open(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    ok += 1
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return ok >= 2


def _print(plain: bool, message: str) -> None:
    # Always plain for deploy MVP; keep accessible.
    print(message)
