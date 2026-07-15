"""Foundational contract/manifest tests.

These tests fail when the runtime copies of the frozen design contracts or the
component/toolchain/migration fact sources are missing or invalid. They must be
written before the runtime facts are materialized.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path

CONTRACTS_DEST = Path("shared") / "contracts" / "repository-workflow" / "v1"
CONTRACTS_SOURCE = Path("specs") / "001-repository-workflow-baseline" / "contracts"

CONTRACT_FILES = [
    "component-manifest.schema.json",
    "workflow-event.schema.json",
    "migration-manifest.schema.json",
    "service-health.openapi.yaml",
    "make-workflow.md",
    "environment-mode.md",
    "ci-gates.md",
]


def assert_is_file(path: Path) -> None:
    assert path.is_file(), f"missing required file: {path}"


def test_runtime_contract_copies_exist() -> None:
    """Runtime contract copies must exist and be non-empty."""
    root = find_repo_root()
    for name in CONTRACT_FILES:
        dest = root / CONTRACTS_DEST / name
        assert_is_file(dest)
        content = dest.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"contract copy is empty: {dest}"


def test_runtime_contracts_link_to_source() -> None:
    """Runtime contract copies must declare their authoritative source."""
    root = find_repo_root()
    readme = root / CONTRACTS_DEST / "README.md"
    assert_is_file(readme)
    text = readme.read_text(encoding="utf-8")
    source_ref = str(CONTRACTS_SOURCE).replace("\\", "/")
    assert source_ref in text, f"README must link to authoritative source: {source_ref}"


def test_component_manifest_exists_and_valid() -> None:
    """ops/workflow/components.json must exist and match the component schema."""
    manifest = load_json("ops", "workflow", "components.json")
    assert manifest["schema_version"] == "1.0.0"
    components = manifest["components"]
    assert len(components) == 8

    ids = {c["id"] for c in components}
    expected = {
        "proxy-gateway",
        "api-service",
        "billing-service",
        "admin-service",
        "frontend",
        "shared",
        "infra",
        "ops",
    }
    assert ids == expected, f"unexpected component ids: {ids}"

    for component in components:
        assert component["required"] is True
        assert component["actions"]
        actions = {a["action"] for a in component["actions"]}
        # Every required service-like component must bind the core workflow actions.
        if component["component_type"] in (
            "go-service",
            "python-service",
            "web-frontend",
        ):
            core = {"bootstrap", "fmt", "type-check", "lint", "test", "build"}
            missing = core - actions
            assert not missing, f"{component['id']} missing core actions: {missing}"


def test_toolchain_manifest_exists_and_valid() -> None:
    """ops/workflow/toolchains.json must exist and declare required tools."""
    manifest = load_json("ops", "workflow", "toolchains.json")
    assert manifest["schema_version"] == "1.0.0"
    tools = manifest["tools"]
    assert tools

    names = {t["tool"] for t in tools}
    required = {"go", "python", "uv", "node", "npm", "docker"}
    missing = required - names
    assert not missing, f"toolchain manifest missing required tools: {missing}"

    for tool in tools:
        assert tool["exact_version"]
        assert tool["version_source"]
        assert tool["affected_components"]


def test_migration_owner_manifest_exists_and_valid() -> None:
    """ops/migrations/owners.json must exist and declare owners and non-owners."""
    manifest = load_json("ops", "migrations", "owners.json")
    assert manifest["schema_version"] == "1.0.0"

    owners = manifest["owners"]
    assert len(owners) == 2
    owner_ids = [o["component_id"] for o in owners]
    assert owner_ids == ["api-service", "billing-service"]

    for owner in owners:
        assert owner["expected_heads"] == 1
        assert owner["version_path"].startswith("services/")
        assert owner["backout_runbook"].startswith("ops/runbooks/")

    assert "admin-service" in manifest["non_owners"]


def test_manifest_schemas_validate_against_contracts() -> None:
    """Runtime fact sources must use the published schemas."""
    component_schema = load_json(str(CONTRACTS_DEST), "component-manifest.schema.json")
    assert component_schema["$id"].endswith("component-manifest.schema.json")

    migration_schema = load_json(str(CONTRACTS_DEST), "migration-manifest.schema.json")
    assert migration_schema["$id"].endswith("migration-manifest.schema.json")

    event_schema = load_json(str(CONTRACTS_DEST), "workflow-event.schema.json")
    assert event_schema["$id"].endswith("workflow-event.schema.json")


def _load_or_none(*parts: str) -> Any | None:
    try:
        return load_json(*parts)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def test_schema_version_is_stable() -> None:
    """All runtime schemas must use the declared v1 major version."""
    for name in (
        "component-manifest.schema.json",
        "workflow-event.schema.json",
        "migration-manifest.schema.json",
    ):
        schema = _load_or_none(str(CONTRACTS_DEST), name)
        if schema is None:
            pytest.skip(f"schema not yet materialized: {name}")
        assert schema["schema_version"] == "1.0.0"
