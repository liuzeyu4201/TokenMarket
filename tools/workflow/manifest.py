"""Component manifest loading and validation.

Validates ``ops/workflow/components.json`` against the published schema and
computes repository-relative paths and action bindings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    """Raised when a manifest violates its contract or repository reality."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


REQUIRED_COMPONENT_IDS = {
    "proxy-gateway",
    "api-service",
    "billing-service",
    "admin-service",
    "frontend",
    "shared",
    "infra",
    "ops",
}

SERVICE_LIKE_TYPES = {"go-service", "python-service", "web-frontend"}
CORE_ACTIONS = {"bootstrap", "fmt", "type-check", "lint", "test", "build"}
UNIVERSAL_ACTIONS = {"bootstrap", "type-check"}
MIGRATION_OWNERS = {"api-service", "billing-service"}


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a component manifest from a path."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate structural rules of the component manifest."""
    if manifest.get("schema_version") != "1.0.0":
        raise ManifestError("manifest schema_version must be 1.0.0")

    components = manifest.get("components")
    if not isinstance(components, list):
        raise ManifestError("components must be a list")

    ids = set()
    for component in components:
        cid = component.get("id")
        if not cid:
            raise ManifestError("component missing id")
        if cid in ids:
            raise ManifestError(f"duplicate component id: {cid}")
        ids.add(cid)

        if component.get("required") is not True:
            raise ManifestError(f"{cid}: required components must have required=true")

        for field in ("path", "owner", "responsibility", "component_type", "test_root"):
            if not component.get(field):
                raise ManifestError(f"{cid}: missing field {field}")

        if not component.get("deliverables"):
            raise ManifestError(f"{cid}: deliverables must be non-empty")

        if not component.get("actions"):
            raise ManifestError(f"{cid}: actions must be non-empty")

        for binding in component.get("actions", []):
            action = binding.get("action")
            adapter = binding.get("adapter")
            if not isinstance(adapter, str) or not adapter.strip():
                raise ManifestError(f"{cid}: empty adapter for action {action}")

    if ids != REQUIRED_COMPONENT_IDS:
        missing = REQUIRED_COMPONENT_IDS - ids
        extra = ids - REQUIRED_COMPONENT_IDS
        raise ManifestError(f"component ids mismatch; missing={missing}, extra={extra}")


def validate_component_action_bindings(manifest: dict[str, Any]) -> None:
    """Validate that component action bindings satisfy the workflow contract."""
    validate_manifest(manifest)

    for component in manifest["components"]:
        cid = component["id"]
        actions = component["actions"]
        action_names = set()

        for binding in actions:
            action = binding.get("action")
            if not action:
                raise ManifestError(f"{cid}: action binding missing action name")
            if action in action_names:
                raise ManifestError(f"{cid}: duplicate action binding {action}")
            action_names.add(action)

            adapter = binding.get("adapter")
            if not isinstance(adapter, str) or not adapter.strip():
                raise ManifestError(f"{cid}: empty adapter for action {action}")

            if binding.get("required") is not True and action in CORE_ACTIONS | UNIVERSAL_ACTIONS:
                raise ManifestError(f"{cid}: action {action} must be required")

        missing_universal = UNIVERSAL_ACTIONS - action_names
        if missing_universal:
            raise ManifestError(f"{cid}: missing universal actions {missing_universal}")

        if component["component_type"] in SERVICE_LIKE_TYPES:
            missing_core = CORE_ACTIONS - action_names
            if missing_core:
                raise ManifestError(f"{cid}: missing core actions {missing_core}")

        has_migrate = "migrate" in action_names
        if has_migrate and cid not in MIGRATION_OWNERS:
            raise ManifestError(f"{cid}: non-owner must not bind migrate action")
        if cid in MIGRATION_OWNERS and not has_migrate:
            raise ManifestError(f"{cid}: migration owner must bind migrate action")


def validate_component_paths(manifest: dict[str, Any], repo_root: Path | None = None) -> None:
    """Validate that declared component paths exist inside the repository."""
    validate_manifest(manifest)
    root = repo_root or Path(__file__).resolve().parents[2]

    for component in manifest["components"]:
        cid = component["id"]
        path = root / component["path"]
        if not path.is_dir():
            raise ManifestError(f"{cid}: component path does not exist: {component['path']}")

        test_root = path / component["test_root"]
        if not test_root.is_dir():
            raise ManifestError(f"{cid}: test_root does not exist: {component['test_root']}")


def validate_test_evidence(manifest: dict[str, Any], repo_root: Path | None = None) -> None:
    """Validate that every component binding test has at least one test file."""
    validate_component_paths(manifest, repo_root)
    root = repo_root or Path(__file__).resolve().parents[2]

    for component in manifest["components"]:
        cid = component["id"]
        has_test = any(a["action"] == "test" and a["required"] for a in component["actions"])
        if not has_test:
            continue

        test_root = root / component["path"] / component["test_root"]
        test_files = (
            list(test_root.rglob("test_*"))
            + list(test_root.rglob("*_test.*"))
            + list(test_root.rglob("*.test.*"))
        )
        if not test_files:
            raise ManifestError(
                f"{cid}: test action bound but no test files in {component['test_root']}"
            )


def validate_all(manifest: dict[str, Any], repo_root: Path | None = None) -> None:
    """Run the full manifest validation suite."""
    validate_component_action_bindings(manifest)
    validate_component_paths(manifest, repo_root)
    validate_test_evidence(manifest, repo_root)


def component_by_id(manifest: dict[str, Any], cid: str) -> dict[str, Any]:
    """Return a component dict by id."""
    for component in manifest["components"]:
        if component["id"] == cid:
            return component
    raise ManifestError(f"component not found: {cid}")


def action_binding(component: dict[str, Any], action: str) -> dict[str, Any]:
    """Return the binding for a component action."""
    for binding in component["actions"]:
        if binding["action"] == action:
            return binding
    raise ManifestError(f"{component['id']}: action {action} not bound")
