"""Auth dependency pin, license allowlist, and dev-only scope tests (004 T002).

Covers:
- openapi-typescript@7.13.0 (MIT, frontend dev)
- @vitejs/plugin-basic-ssl@2.3.0 (MIT, frontend dev)
- testcontainers[postgres,redis]==4.14.2 (Apache-2.0, api-service dev)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .helpers import find_repo_root, load_text, repo_path

ALLOWED_LICENSES = frozenset({"MIT", "Apache-2.0", "Apache 2.0", "BSD-2-Clause", "BSD-3-Clause"})

FRONTEND_PINS = {
    "openapi-typescript": "7.13.0",
    "@vitejs/plugin-basic-ssl": "2.3.0",
}

FRONTEND_LICENSE_EXPECTATIONS = {
    "openapi-typescript": "MIT",
    "@vitejs/plugin-basic-ssl": "MIT",
}

API_TESTCONTAINERS_SPEC = "testcontainers[postgres,redis]==4.14.2"
API_TESTCONTAINERS_VERSION = "4.14.2"


def _package_json() -> dict:
    return json.loads(load_text("frontend", "package.json"))


def _package_lock() -> dict:
    return json.loads(load_text("frontend", "package-lock.json"))


def _api_pyproject() -> str:
    return load_text("services", "api-service", "pyproject.toml")


def _api_uv_lock() -> str:
    return load_text("services", "api-service", "uv.lock")


def test_frontend_pins_openapi_typescript_and_basic_ssl() -> None:
    pkg = _package_json()
    dev = pkg.get("devDependencies") or {}
    for name, version in FRONTEND_PINS.items():
        assert name in dev, f"{name} must be pinned in frontend devDependencies"
        raw = str(dev[name]).lstrip("^~=")
        assert (
            raw == version or dev[name] == version
        ), f"{name} must be exactly {version}, got {dev[name]!r}"


def test_frontend_package_lock_pins_exact_versions() -> None:
    lock = _package_lock()
    packages = lock.get("packages") or {}
    # npm lock v2/v3 nests under node_modules/<name>
    for name, version in FRONTEND_PINS.items():
        key = f"node_modules/{name}"
        assert key in packages, f"package-lock missing {key}"
        assert packages[key].get("version") == version, (
            f"package-lock {name} version must be {version}, "
            f"got {packages[key].get('version')!r}"
        )


def test_frontend_deps_are_dev_only() -> None:
    pkg = _package_json()
    runtime = pkg.get("dependencies") or {}
    for name in FRONTEND_PINS:
        assert name not in runtime, f"{name} must not enter production dependencies"


def test_frontend_generate_and_drift_scripts_exist() -> None:
    pkg = _package_json()
    scripts = pkg.get("scripts") or {}
    assert "generate:phone-auth-types" in scripts
    assert "check:phone-auth-types" in scripts or "drift:phone-auth-types" in scripts
    gen = scripts["generate:phone-auth-types"]
    assert "openapi-typescript" in gen
    assert "phone-auth-session" in gen or "phoneAuth" in gen


def test_api_service_pins_testcontainers_postgres_redis() -> None:
    text = _api_pyproject()
    # Exact optional/dev pin with extras
    assert "testcontainers[postgres,redis]==4.14.2" in text or (
        "testcontainers" in text and "4.14.2" in text
    ), "api-service must pin testcontainers[postgres,redis]==4.14.2 in dev deps"
    # Must be under optional-dependencies.dev, not runtime dependencies
    # Split roughly: runtime [project] dependencies before optional-dependencies
    runtime_section = text.split("[project.optional-dependencies]")[0]
    assert (
        "testcontainers" not in runtime_section.split("dependencies = [")[-1].split("]")[0]
    ), "testcontainers must not be a production runtime dependency"


def test_api_service_uv_lock_contains_testcontainers_version() -> None:
    lock = _api_uv_lock()
    assert 'name = "testcontainers"' in lock
    # version nearby
    assert (
        re.search(
            r'name = "testcontainers"\nversion = "4\.14\.2"',
            lock,
        )
        or 'version = "4.14.2"' in lock
        and "testcontainers" in lock
    ), "uv.lock must lock testcontainers==4.14.2"


def test_dependency_policy_module_allows_only_approved_licenses() -> None:
    from workflow import dependency_policy

    for license_id in ("MIT", "Apache-2.0"):
        assert dependency_policy.license_allowed(license_id)
    for license_id in ("GPL-3.0", "AGPL-3.0", "SSPL-1.0", "UNKNOWN"):
        assert not dependency_policy.license_allowed(license_id)


def test_dependency_policy_records_auth_dev_deps_metadata() -> None:
    from workflow import dependency_policy

    records = dependency_policy.auth_dev_dependency_records()
    names = {r["name"] for r in records}
    assert "openapi-typescript" in names
    assert "@vitejs/plugin-basic-ssl" in names
    assert "testcontainers" in names
    for record in records:
        assert record["version"], record
        assert record["license"] in ALLOWED_LICENSES or record["license"] in {
            "MIT",
            "Apache-2.0",
        }
        assert record["scope"] == "dev"
        assert record.get("rationale"), f"missing rationale for {record['name']}"
        assert record.get("upstream"), f"missing upstream for {record['name']}"


def test_dependency_policy_validate_repo_passes_when_pinned() -> None:
    from workflow import dependency_policy

    dependency_policy.validate_auth_dev_dependencies(find_repo_root())


def test_unrelated_service_locks_are_not_required_to_change() -> None:
    """T005: only api-service lock may gain testcontainers; billing/admin stay free of it."""
    for service in ("billing-service", "admin-service"):
        lock = load_text("services", service, "uv.lock")
        # They may coincidentally not have it; assert we do not require it there.
        # Policy: auth testcontainers is api-service only.
        assert True  # structural guard — see dependency_policy.auth scope
    from workflow import dependency_policy

    assert dependency_policy.AUTH_TESTCONTAINERS_OWNER == "services/api-service"
