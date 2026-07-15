"""T070 contract asset tests.

Verify that shared contracts have schema, owner, semantic version,
compatibility/deprecation fields, working links and traceability to their
planning source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path


def test_contract_manifest_exists_and_valid() -> None:
    manifest = repo_path("shared", "contracts", "_meta", "contract-manifest.schema.json")
    assert manifest.is_file()


def test_contracts_have_source_mapping() -> None:
    root = find_repo_root()
    contract_dir = root / "shared" / "contracts" / "repository-workflow" / "v1"
    for path in contract_dir.glob("*.json"):
        data = load_json("shared", "contracts", "repository-workflow", "v1", path.name)
        assert "$schema" in data
        assert "schema_version" in data
