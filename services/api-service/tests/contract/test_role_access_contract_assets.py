"""Contract assets for role-access-isolation v1 must exist and parse."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_DIR = ROOT / "shared" / "contracts" / "role-access-isolation" / "v1"


def test_contract_files_exist() -> None:
    assert (CONTRACT_DIR / "role-access-isolation.openapi.yaml").is_file()
    assert (CONTRACT_DIR / "business-codes.md").is_file()
    assert (CONTRACT_DIR / "authorization-matrix.md").is_file()


def test_openapi_parses() -> None:
    pytest.importorskip("yaml")
    import yaml

    text = (CONTRACT_DIR / "role-access-isolation.openapi.yaml").read_text()
    doc = yaml.safe_load(text)
    assert doc["openapi"].startswith("3.")
    paths = doc["paths"]
    assert "/authorization/evaluate" in paths
    assert "/authorization/route-candidates/exclude-self" in paths
