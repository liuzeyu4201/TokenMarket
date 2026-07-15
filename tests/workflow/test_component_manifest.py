"""Component manifest validation tests (T016).

These tests exercise the manifest loader/validator that will be implemented in
``tools/workflow/manifest.py``. They verify:

* eight required components are declared and complete;
* every applicable component binds ``bootstrap``, ``type-check`` and the other
  required actions;
* negative cases reject empty adapters, uninitialized components and components
  that claim a ``test`` action but contain zero test evidence.

Because ``workflow.manifest`` does not yet exist, the tests fail with an
``ImportError``/``AttributeError`` that points directly at the missing
implementation.
"""

from __future__ import annotations

import copy
import importlib  # Imported inside tests so collection succeeds before T030/T031.
import json
from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path


def _manifest_module():
    try:
        return importlib.import_module("workflow.manifest")
    except ImportError as exc:
        pytest.fail(f"workflow.manifest has not been implemented yet (T031): {exc}")


def _manifest_error():
    return getattr(_manifest_module(), "ManifestError")


def _validate_manifest(manifest):
    return getattr(_manifest_module(), "validate_manifest")(manifest)


def _validate_component_action_bindings(manifest):
    return getattr(_manifest_module(), "validate_component_action_bindings")(manifest)


def _validate_component_paths(manifest):
    return getattr(_manifest_module(), "validate_component_paths")(manifest)


def _validate_test_evidence(manifest):
    return getattr(_manifest_module(), "validate_test_evidence")(manifest)


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

# Service-like components must bind the full core workflow.
SERVICE_LIKE_TYPES = {"go-service", "python-service", "web-frontend"}
CORE_ACTIONS = {"bootstrap", "fmt", "type-check", "lint", "test", "build"}

# Every component, including asset-only components, must support bootstrap and
# the stable type-check support target.
UNIVERSAL_ACTIONS = {"bootstrap", "type-check"}


def _manifest() -> dict[str, Any]:
    return load_json("ops", "workflow", "components.json")


def _write_tmp_manifest(tmp_path: Path, manifest: dict[str, Any]) -> Path:
    path = tmp_path / "components.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_eight_required_components_are_complete() -> None:
    """The manifest must declare exactly the eight required components."""
    manifest = _manifest()
    _validate_manifest(manifest)

    components = manifest["components"]
    assert len(components) == 8

    ids = {c["id"] for c in components}
    assert ids == REQUIRED_COMPONENT_IDS

    for component in components:
        assert component["required"] is True
        assert component["path"]
        assert component["owner"]
        assert component["responsibility"]
        assert component["component_type"]
        assert component["test_root"]
        assert component["deliverables"]
        assert component["actions"]


def test_service_like_components_bind_core_actions() -> None:
    """Deployable service/front-end components must bind all core actions."""
    manifest = _manifest()
    _validate_component_action_bindings(manifest)

    for component in manifest["components"]:
        actions = {a["action"] for a in component["actions"]}

        # Universal support targets are required for every component.
        missing_universal = UNIVERSAL_ACTIONS - actions
        assert (
            not missing_universal
        ), f"{component['id']} missing universal actions: {missing_universal}"

        # Service-like components additionally require the full core set.
        if component["component_type"] in SERVICE_LIKE_TYPES:
            missing_core = CORE_ACTIONS - actions
            assert not missing_core, f"{component['id']} missing core actions: {missing_core}"


def test_migration_owners_bind_migrate_action() -> None:
    """Only declared migration owners may bind the migrate action."""
    manifest = _manifest()
    _validate_component_action_bindings(manifest)

    migration_owners = {"api-service", "billing-service"}
    for component in manifest["components"]:
        actions = {a["action"] for a in component["actions"]}
        has_migrate = "migrate" in actions
        if component["id"] in migration_owners:
            assert has_migrate, f"{component['id']} must bind migrate action"
        else:
            assert not has_migrate, f"{component['id']} must not bind migrate action"


def test_empty_adapter_is_rejected(tmp_path: Path) -> None:
    """A binding with an empty adapter string must fail validation."""
    manifest = _manifest()
    component = next(c for c in manifest["components"] if c["id"] == "api-service")
    component["actions"][0]["adapter"] = ""

    path = _write_tmp_manifest(tmp_path, manifest)

    with pytest.raises(_manifest_error()) as exc:
        _validate_component_action_bindings(load_json(str(path)))

    assert "empty adapter" in str(exc.value).lower()


def test_uninitialized_component_path_is_rejected(tmp_path: Path) -> None:
    """A required component whose declared path does not exist is uninitialized."""
    manifest = _manifest()
    component = next(c for c in manifest["components"] if c["id"] == "admin-service")
    component["path"] = "services/admin-service-does-not-exist"

    path = _write_tmp_manifest(tmp_path, manifest)

    with pytest.raises(_manifest_error()) as exc:
        _validate_component_paths(load_json(str(path)))

    assert "admin-service" in str(exc.value)


def test_zero_test_evidence_is_rejected(tmp_path: Path) -> None:
    """A component binding ``test`` must contain at least one test file."""
    manifest = _manifest()
    component = next(c for c in manifest["components"] if c["id"] == "frontend")
    # Point the test root at an empty directory so no test evidence exists.
    component["test_root"] = "src/assets/empty-test-root"

    root = find_repo_root()
    empty_root = root / component["path"] / component["test_root"]
    empty_root.mkdir(parents=True, exist_ok=True)

    try:
        path = _write_tmp_manifest(tmp_path, manifest)
        with pytest.raises(_manifest_error()) as exc:
            _validate_test_evidence(load_json(str(path)))
        assert "frontend" in str(exc.value)
        assert "test" in str(exc.value).lower()
    finally:
        # Clean up the synthetic empty directory.
        if empty_root.exists():
            empty_root.rmdir()


def test_duplicate_component_id_is_rejected(tmp_path: Path) -> None:
    """Duplicate component IDs must be detected and rejected."""
    manifest = _manifest()
    duplicate = copy.deepcopy(manifest["components"][0])
    manifest["components"].append(duplicate)

    path = _write_tmp_manifest(tmp_path, manifest)

    with pytest.raises(_manifest_error()) as exc:
        _validate_manifest(load_json(str(path)))

    assert "duplicate" in str(exc.value).lower()


def test_required_action_must_be_marked_required(tmp_path: Path) -> None:
    """Core required actions must not be marked optional in the manifest."""
    manifest = _manifest()
    component = next(c for c in manifest["components"] if c["id"] == "proxy-gateway")
    bootstrap = next(a for a in component["actions"] if a["action"] == "bootstrap")
    bootstrap["required"] = False

    path = _write_tmp_manifest(tmp_path, manifest)

    with pytest.raises(_manifest_error()) as exc:
        _validate_component_action_bindings(load_json(str(path)))

    assert "bootstrap" in str(exc.value).lower()
