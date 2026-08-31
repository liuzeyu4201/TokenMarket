"""Dependency governance for authentication feature (004).

Validates accurate pins, lockfiles, MIT/Apache-2.0 allowlist membership,
dev-only scope, and reviewed metadata for the three auth-related dev dependencies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_LICENSES: frozenset[str] = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "Apache 2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Python-2.0",
        "Unlicense",
        "CC0-1.0",
    }
)

AUTH_TESTCONTAINERS_OWNER = "services/api-service"

# Reviewed 2026-07-25 (see specs/004-phone-login-session-ui/research.md Decision 19).
_AUTH_DEV_DEPS: tuple[dict[str, str], ...] = (
    {
        "name": "openapi-typescript",
        "version": "7.13.0",
        "license": "MIT",
        "scope": "dev",
        "owner": "frontend",
        "upstream": "https://www.npmjs.com/package/openapi-typescript",
        "rationale": (
            "Generate runtime-free TypeScript types from local OpenAPI so "
            "Frontend cannot drift from the shared phone-auth contract."
        ),
    },
    {
        "name": "@vitejs/plugin-basic-ssl",
        "version": "2.3.0",
        "license": "MIT",
        "scope": "dev",
        "owner": "frontend",
        "upstream": "https://www.npmjs.com/package/@vitejs/plugin-basic-ssl",
        "rationale": (
            "Local Vite HTTPS so Secure/HttpOnly session cookies work during "
            "same-origin development without production TLS infrastructure."
        ),
    },
    {
        "name": "testcontainers",
        "version": "4.14.2",
        "license": "Apache-2.0",
        "scope": "dev",
        "owner": AUTH_TESTCONTAINERS_OWNER,
        "extras": "postgres,redis",
        "upstream": "https://pypi.org/project/testcontainers/",
        "rationale": (
            "Real PostgreSQL 15 and Redis 7 integration tests for locks, "
            "constraints, Lua rate limits, and concurrent session invariants."
        ),
    },
)


def license_allowed(license_id: str) -> bool:
    """Return True if *license_id* is on the approved open-source allowlist."""
    normalized = license_id.strip()
    if normalized in ALLOWED_LICENSES:
        return True
    # Accept SPDX expressions that are pure allowlisted tokens joined by OR
    if " OR " in normalized.upper():
        parts = [p.strip() for p in re.split(r"\s+OR\s+", normalized, flags=re.I)]
        return all(p in ALLOWED_LICENSES for p in parts)
    return False


def auth_dev_dependency_records() -> list[dict[str, str]]:
    """Return the reviewed auth dev-dependency metadata records."""
    return [dict(item) for item in _AUTH_DEV_DEPS]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_auth_dev_dependencies(repo_root: Path) -> None:
    """Fail closed if auth dev dependencies are missing, unpinned, or mis-scoped.

    Raises ``ValueError`` with variable/package names only (no secrets).
    """
    for record in _AUTH_DEV_DEPS:
        if not license_allowed(record["license"]):
            raise ValueError(
                f"auth dependency {record['name']!r} license {record['license']!r} "
                "is not on the approved allowlist"
            )

    pkg_path = repo_root / "frontend" / "package.json"
    lock_path = repo_root / "frontend" / "package-lock.json"
    if not pkg_path.is_file():
        raise ValueError("frontend/package.json is required")
    if not lock_path.is_file():
        raise ValueError("frontend/package-lock.json is required")

    package = _load_json(pkg_path)
    lock = _load_json(lock_path)
    dev = package.get("devDependencies") or {}
    runtime = package.get("dependencies") or {}
    packages = lock.get("packages") or {}

    for name, version in (
        ("openapi-typescript", "7.13.0"),
        ("@vitejs/plugin-basic-ssl", "2.3.0"),
    ):
        if name not in dev:
            raise ValueError(f"{name} must be pinned in frontend devDependencies")
        pinned = str(dev[name]).lstrip("^~=")
        if pinned != version and dev[name] != version:
            raise ValueError(f"{name} must be exactly {version}, found {dev[name]!r}")
        if name in runtime:
            raise ValueError(f"{name} must not appear in frontend production dependencies")
        key = f"node_modules/{name}"
        entry = packages.get(key)
        if not entry or entry.get("version") != version:
            raise ValueError(f"frontend package-lock.json must lock {name}@{version}")

    scripts = package.get("scripts") or {}
    if "generate:phone-auth-types" not in scripts:
        raise ValueError("frontend scripts must define generate:phone-auth-types")
    if "check:phone-auth-types" not in scripts and "drift:phone-auth-types" not in scripts:
        raise ValueError(
            "frontend scripts must define check:phone-auth-types or drift:phone-auth-types"
        )

    pyproject = repo_root / "services" / "api-service" / "pyproject.toml"
    uv_lock = repo_root / "services" / "api-service" / "uv.lock"
    if not pyproject.is_file():
        raise ValueError("services/api-service/pyproject.toml is required")
    if not uv_lock.is_file():
        raise ValueError("services/api-service/uv.lock is required")

    py_text = pyproject.read_text(encoding="utf-8")
    if "testcontainers" not in py_text or "4.14.2" not in py_text:
        raise ValueError("services/api-service must pin testcontainers 4.14.2 in dev dependencies")
    if "postgres" not in py_text or "redis" not in py_text:
        # extras may be written as testcontainers[postgres,redis]
        if "testcontainers[postgres,redis]" not in py_text:
            raise ValueError("testcontainers must request postgres and redis extras")

    # Ensure testcontainers is not in the primary runtime dependency table.
    runtime_match = re.search(
        r"(?ms)^dependencies\s*=\s*\[(.*?)\]",
        py_text.split("[project.optional-dependencies]")[0],
    )
    if runtime_match and "testcontainers" in runtime_match.group(1):
        raise ValueError("testcontainers must not be an api-service runtime dependency")

    lock_text = uv_lock.read_text(encoding="utf-8")
    if 'name = "testcontainers"' not in lock_text:
        raise ValueError("services/api-service/uv.lock must include testcontainers")
    if not re.search(r'version = "4\.14\.2"', lock_text):
        raise ValueError("services/api-service/uv.lock must lock version 4.14.2")
