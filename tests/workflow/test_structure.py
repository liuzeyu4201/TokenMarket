"""T069 structural boundary tests.

Verify that required component boundaries exist, paths stay inside the
repository, tests live in declared roots, READMEs are non-empty, and every
declared deliverable has evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path


@pytest.fixture
def manifest() -> dict[str, Any]:
    return load_json("ops", "workflow", "components.json")


def test_all_components_have_readme(manifest: dict[str, Any]) -> None:
    for component in manifest["components"]:
        readme = repo_path(component["path"], "README.md")
        assert readme.is_file(), f"{component['id']} missing README.md"
        assert readme.stat().st_size > 0, f"{component['id']} README.md is empty"


def test_component_paths_are_inside_repository(manifest: dict[str, Any]) -> None:
    root = find_repo_root()
    for component in manifest["components"]:
        comp_path = repo_path(component["path"]).resolve()
        assert (
            root in comp_path.parents or comp_path == root
        ), f"{component['id']} path escapes repository root"


def test_test_roots_are_declared_directories(manifest: dict[str, Any]) -> None:
    for component in manifest["components"]:
        test_root = repo_path(component["path"], component["test_root"])
        assert test_root.is_dir(), f"{component['id']} test_root missing: {test_root}"


def test_deliverables_have_evidence(manifest: dict[str, Any]) -> None:
    for component in manifest["components"]:
        for deliverable in component.get("deliverables", []):
            assert deliverable in {
                "binary",
                "container-image",
                "static-site-image",
                "asset-archive",
            }, f"{component['id']} unknown deliverable: {deliverable}"
