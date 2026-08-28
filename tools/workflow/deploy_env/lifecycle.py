"""Minimal deploy-stack lifecycle for ``make deploy`` / ``make deploy-down``.

Implements ADR 003 Layer D: merge middleware + app Compose files under a
fixed environment project name, inject child-only env, never delete volumes
on ordinary down. Secrets are read from ignored ``.env.test`` / ``.env.prod``.

Feature 004 auth release gate
-----------------------------
When ``AUTH_RELEASE_MANIFEST`` (or Make ``auth_release_manifest=…``) is set,
``deploy_up`` calls :func:`verify_auth_release_manifest` *before* Docker so
missing manifests, bad companion hashes, incomplete evidence bindings, or
synthetic/prod-unsafe activation fail closed. This is intentionally decoupled
from real ``specs/004-…/evidence/`` paths — unit tests use synthetic fixtures
under ``tests/workflow/fixtures/auth-release/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
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

# P1/P2 blocking evidence keys that must be bound in an auth release manifest.
REQUIRED_AUTH_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "quality_gates",
        "api_performance",
        "browser",
        "backup_restore",
        "quickstart",
        "traceability",
    }
)

# SMS adapters that must never activate production authentication.
_SYNTHETIC_SMS_ADAPTERS: frozenset[str] = frozenset(
    {
        "",
        "synthetic",
        "fake",
        "mock",
        "null",
        "none",
        "disabled",
    }
)

_DIGEST_RE = re.compile(r"^sha256:[a-fA-F0-9]{64}$")


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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def auth_release_companion_path(manifest_path: Path) -> Path:
    """Sibling ``.sha256`` companion next to the auth release manifest JSON."""
    return manifest_path.with_suffix(manifest_path.suffix + ".sha256")


def resolve_auth_release_manifest_path(
    raw: str | Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    path = Path(raw)
    if not path.is_absolute() and repo_root is not None:
        path = repo_root / path
    return path


def verify_auth_release_manifest(
    path: str | Path,
    *,
    repo_root: Path | None = None,
    require_activation: bool = True,
    target_mode: str | None = None,
) -> dict[str, Any]:
    """Fail-closed verification of an auth release candidate + evidence binding.

    Checks (in order):
    1. Manifest file exists and is a JSON object.
    2. Sibling ``.sha256`` companion exists and matches the JSON bytes.
    3. Required top-level fields and every :data:`REQUIRED_AUTH_EVIDENCE_KEYS`
       entry is present under ``evidence`` with a non-empty ``sha256``.
    4. Image/frontend digests look like ``sha256:<64 hex>`` when present.
    5. When ``require_activation`` is true, the ``activation`` block is present
       and fail-closed for TLS, approved SMS, trusted proxy/origin, keys,
       dispatcher, and cleanup schedule — especially for ``target_mode=prod``.

    Never loads real secrets; activation only carries non-secret readiness flags
    and adapter *names*. Evidence paths are opaque strings (synthetic fixtures
    or repo-relative evidence paths) and are not opened here.
    """
    manifest_path = resolve_auth_release_manifest_path(path, repo_root=repo_root)
    if not manifest_path.is_file():
        raise DeployError(
            "AUTH_MANIFEST_MISSING",
            f"auth release manifest not found: {manifest_path}",
        )

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeployError(
            "AUTH_MANIFEST_INVALID",
            f"auth release manifest is not JSON: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise DeployError("AUTH_MANIFEST_INVALID", "auth release manifest root must be an object")

    companion = auth_release_companion_path(manifest_path)
    if not companion.is_file():
        raise DeployError(
            "AUTH_COMPANION_MISSING",
            f"auth release sha256 companion missing: {companion}",
        )
    recorded = companion.read_text(encoding="utf-8").strip().split()[0]
    actual = _sha256_file(manifest_path)
    if recorded != actual:
        raise DeployError(
            "AUTH_HASH_MISMATCH",
            "auth release manifest sha256 does not match companion",
        )

    required_top = (
        "schema_version",
        "kind",
        "increment",
        "commit_sha",
        "evidence",
    )
    for key in required_top:
        if key not in payload:
            raise DeployError(
                "AUTH_MANIFEST_INVALID",
                f"auth release manifest missing field {key!r}",
            )

    kind = payload.get("kind")
    if kind not in (
        "tokenmarket.auth_release_manifest",
        "tokenmarket.release_candidate",
    ):
        raise DeployError(
            "AUTH_MANIFEST_INVALID",
            f"unexpected auth release kind {kind!r}",
        )

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise DeployError("AUTH_EVIDENCE_MISSING", "evidence must be an object")

    missing_keys = sorted(REQUIRED_AUTH_EVIDENCE_KEYS - set(evidence.keys()))
    if missing_keys:
        raise DeployError(
            "AUTH_EVIDENCE_MISSING",
            "required evidence keys missing: " + ", ".join(missing_keys),
        )

    for key in sorted(REQUIRED_AUTH_EVIDENCE_KEYS):
        entry = evidence[key]
        if not isinstance(entry, dict):
            raise DeployError(
                "AUTH_EVIDENCE_INVALID",
                f"evidence.{key} must be an object with path/sha256",
            )
        digest = str(entry.get("sha256") or "").strip()
        if not digest:
            raise DeployError(
                "AUTH_EVIDENCE_INVALID",
                f"evidence.{key} missing sha256 binding",
            )
        # Accept either bare hex or sha256:hex forms.
        bare = digest.removeprefix("sha256:")
        if len(bare) != 64 or any(c not in "0123456789abcdefABCDEF" for c in bare):
            raise DeployError(
                "AUTH_EVIDENCE_INVALID",
                f"evidence.{key} sha256 is not a 64-hex digest",
            )

    image_digests = payload.get("image_digests") or {}
    if image_digests is not None and not isinstance(image_digests, dict):
        raise DeployError("AUTH_DIGEST_INVALID", "image_digests must be an object")
    if isinstance(image_digests, dict):
        for name, digest in image_digests.items():
            if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
                raise DeployError(
                    "AUTH_DIGEST_MISMATCH",
                    f"image_digests[{name!r}] is not a sha256:<64hex> digest",
                )

    frontend_digest = payload.get("frontend_digest")
    if frontend_digest is not None:
        if not isinstance(frontend_digest, str) or not _DIGEST_RE.fullmatch(frontend_digest):
            raise DeployError(
                "AUTH_DIGEST_MISMATCH",
                "frontend_digest is not a sha256:<64hex> digest",
            )

    activation_report: dict[str, Any] | None = None
    if require_activation:
        activation_report = verify_auth_activation(
            payload.get("activation"),
            target_mode=target_mode,
        )

    return {
        "ok": True,
        "path": str(manifest_path),
        "manifest_sha256": actual,
        "increment": payload.get("increment"),
        "commit_sha": payload.get("commit_sha"),
        "evidence_keys": sorted(REQUIRED_AUTH_EVIDENCE_KEYS),
        "activation": activation_report,
    }


def verify_auth_activation(
    activation: Any,
    *,
    target_mode: str | None = None,
) -> dict[str, Any]:
    """Fail-closed auth activation checks (TLS, SMS, proxy, keys, dispatcher, cleanup).

    ``activation`` is a non-secret readiness object embedded in the release
    manifest. Real key material must never appear here — only booleans/names.
    """
    if not isinstance(activation, Mapping):
        raise DeployError(
            "AUTH_ACTIVATION_MISSING",
            "activation block missing from auth release manifest",
        )

    mode = (target_mode or "").strip().lower() or None
    tls_ready = bool(activation.get("tls_ready"))
    sms_adapter = str(activation.get("sms_adapter") or "").strip().lower()
    origins = activation.get("browser_origins") or []
    proxies = activation.get("trusted_proxy_cidrs") or []
    keys_ok = bool(activation.get("hmac_keys_configured"))
    dispatcher_enabled = bool(activation.get("dispatcher_enabled"))
    cleanup_cron = str(activation.get("cleanup_schedule_cron") or "").strip()
    cleanup_batch = activation.get("cleanup_batch_size")
    cleanup_runtime = activation.get("cleanup_max_runtime_seconds")

    if not isinstance(origins, list) or not origins:
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation.browser_origins must be a non-empty list",
        )
    if not isinstance(proxies, list) or not proxies:
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation.trusted_proxy_cidrs must be a non-empty list",
        )
    if not keys_ok:
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation.hmac_keys_configured must be true (flags only; no secret values)",
        )
    if not dispatcher_enabled:
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation.dispatcher_enabled must be true for auth release",
        )
    if cleanup_cron != "17 * * * *":
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation.cleanup_schedule_cron must be UTC '17 * * * *'",
        )
    try:
        if int(cleanup_batch) != 500:  # type: ignore[arg-type]
            raise DeployError(
                "AUTH_ACTIVATION_INVALID",
                "activation.cleanup_batch_size must be 500",
            )
        if int(cleanup_runtime) != 900:  # type: ignore[arg-type]
            raise DeployError(
                "AUTH_ACTIVATION_INVALID",
                "activation.cleanup_max_runtime_seconds must be 900",
            )
    except (TypeError, ValueError) as exc:
        raise DeployError(
            "AUTH_ACTIVATION_INVALID",
            "activation cleanup batch/runtime must be integers 500/900",
        ) from exc

    # Prod (and any explicit non-test release) forbids synthetic SMS / unready TLS.
    strict = mode in (None, "prod", "test")
    if strict:
        if not tls_ready:
            raise DeployError(
                "AUTH_ACTIVATION_TLS",
                "activation.tls_ready must be true for auth release deploy",
            )
        if sms_adapter in _SYNTHETIC_SMS_ADAPTERS:
            raise DeployError(
                "AUTH_ACTIVATION_SMS",
                "activation.sms_adapter must be an approved non-synthetic provider",
            )

    return {
        "ok": True,
        "tls_ready": tls_ready,
        "sms_adapter": sms_adapter,
        "dispatcher_enabled": dispatcher_enabled,
        "cleanup_schedule_cron": cleanup_cron,
        "target_mode": mode,
    }


def auth_release_manifest_from_env() -> str | None:
    """Read optional auth release path from Make/env (no public Make target)."""
    for key in ("AUTH_RELEASE_MANIFEST", "auth_release_manifest"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


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


# Auth hooks for compose.app.yml. Always written into child env so Compose can use
# strict ${TOKENMARKET_DEPLOY_*} interpolation (no ${VAR:-default} forms).
# Empty optional strings are explicit; numeric/flag defaults match prior scaffolding.
_AUTH_CHILD_ENV_DEFAULTS: tuple[tuple[str, str, str], ...] = (
    # (child_env key, optional dotenv key, explicit default when absent)
    ("TOKENMARKET_DEPLOY_AUTH_BROWSER_ORIGINS", "AUTH_BROWSER_ORIGINS", ""),
    ("TOKENMARKET_DEPLOY_AUTH_TRUSTED_PROXY_CIDRS", "AUTH_TRUSTED_PROXY_CIDRS", ""),
    ("TOKENMARKET_DEPLOY_AUTH_SMS_ADAPTER", "AUTH_SMS_ADAPTER", ""),
    (
        "TOKENMARKET_DEPLOY_AUTH_DISPATCHER_LEASE_SECONDS",
        "AUTH_DISPATCHER_LEASE_SECONDS",
        "30",
    ),
    (
        "TOKENMARKET_DEPLOY_AUTH_DISPATCHER_DRAIN_SECONDS",
        "AUTH_DISPATCHER_DRAIN_SECONDS",
        "15",
    ),
    (
        "TOKENMARKET_DEPLOY_AUTH_DISPATCHER_ENABLED",
        "AUTH_DISPATCHER_ENABLED",
        "1",
    ),
    ("TOKENMARKET_DEPLOY_AUTH_CLEANUP_BATCH_SIZE", "AUTH_CLEANUP_BATCH_SIZE", "500"),
    (
        "TOKENMARKET_DEPLOY_AUTH_CLEANUP_MAX_RUNTIME_SECONDS",
        "AUTH_CLEANUP_MAX_RUNTIME_SECONDS",
        "900",
    ),
    ("TOKENMARKET_DEPLOY_AUTH_TLS_READY", "AUTH_TLS_READY", "false"),
)


def _auth_deploy_child_env(raw: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build explicit TOKENMARKET_DEPLOY_AUTH_* values for Compose interpolation.

    Missing keys are still emitted (empty string or scaffolding default) so
    defaults never hide in Compose ``:-`` expressions.
    """
    source = raw or {}
    out: dict[str, str] = {}
    for child_key, dotenv_key, default in _AUTH_CHILD_ENV_DEFAULTS:
        if dotenv_key in source:
            out[child_key] = str(source[dotenv_key]).strip()
        else:
            out[child_key] = default
    return out


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
        if selection.mode == "prod":
            from ..image_pin import require_digest_pinned_image

            images[key] = require_digest_pinned_image(image, name=key)

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
        **_auth_deploy_child_env(raw),
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
        cfg = None
        if selection.mode == "prod":
            cfg = load_deploy_config(repo_root, selection)
            from ..image_pin import verify_approved_digests

            raw_proof = os.environ.get("TOKENMARKET_PROD_APPROVAL") or ""
            proof = json.loads(raw_proof) if raw_proof else None
            selection = require_production_approval(
                selection,
                approval_proof=proof,
                action="deploy",
                target=cfg.project_name,
                image_digests=tuple(cfg.app_images),
            )
            verify_approved_digests(cfg.app_images)

        # Optional feature-004 auth release gate (Make: auth_release_manifest=…).
        # Runs before Docker so missing/bad manifests fail closed without side effects.
        auth_manifest = auth_release_manifest_from_env()
        if auth_manifest:
            verify_auth_release_manifest(
                auth_manifest,
                repo_root=repo_root,
                require_activation=True,
                target_mode=selection.mode,
            )
            _print(
                plain,
                f"[PASSED] auth-release-manifest path={auth_manifest} mode={selection.mode}",
            )

        _ensure_docker()
        if cfg is None:
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
            **_auth_deploy_child_env(),
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
