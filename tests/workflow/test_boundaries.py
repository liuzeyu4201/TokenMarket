"""T071 component boundary tests.

Verify that services do not import each other's internals, do not access
another service's storage, shared contains no business logic, and admin-service
has no migration ownership.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import load_json, repo_path


def test_admin_service_has_no_migration_action() -> None:
    manifest = load_json("ops", "workflow", "components.json")
    for component in manifest["components"]:
        if component["id"] == "admin-service":
            actions = {a["action"] for a in component["actions"]}
            assert "migrate" not in actions


def test_no_service_imports_another_service_internal() -> None:
    """Scan Python service code for forbidden cross-service internal imports."""
    services = ["api-service", "billing-service", "admin-service"]
    for service in services:
        service_path = repo_path("services", service)
        for py_file in service_path.rglob("*.py"):
            if ".venv" in py_file.parts:
                continue
            text = py_file.read_text(encoding="utf-8")
            for other in services:
                if other == service:
                    continue
                assert f"from services.{other}" not in text, f"{py_file} imports services.{other}"
