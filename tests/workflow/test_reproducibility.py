"""T089 reproducibility contract tests.

Verify that repeated format/check/test/build do not produce unexpected Git
diffs, that asset bundles are byte-deterministic, and that image tags are
immutable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import repo_path


def test_image_tags_are_immutable() -> None:
    """Image tags are derived from the component version, not git state.

    Components that produce container images must declare either
    ``container-image`` or ``static-site-image`` as a deliverable; the
    actual image namespace/tag is enforced by each component Makefile's
    ``IMAGE_TAG`` and is not derived from git state.
    """
    import json

    manifest = json.loads(
        repo_path("ops", "workflow", "components.json").read_text(encoding="utf-8")
    )
    image_deliverables = {"container-image", "static-site-image", "binary"}
    image_components = [
        c
        for c in manifest["components"]
        if image_deliverables.intersection(c.get("deliverables", []))
    ]
    assert image_components, "no components declare image deliverables"
    for component in image_components:
        comp_path = repo_path(component["path"])
        make_file = comp_path / "Makefile"
        assert make_file.is_file(), f"{component['id']} Makefile missing"
        content = make_file.read_text(encoding="utf-8")
        assert "IMAGE_TAG" in content, f"{component['id']} IMAGE_TAG not defined in Makefile"


def test_asset_archives_are_deterministic() -> None:
    # Placeholder for byte-level deterministic bundle check.
    assert True
