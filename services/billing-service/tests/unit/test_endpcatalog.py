"""API service catalog major-version fail-closed gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.endpcatalog import CatalogError, load_catalog


def test_load_matching_major(tmp_path: Path) -> None:
    payload = {
        "schema_version": "1.0.0",
        "catalog_major": 1,
        "catalog_minor": 0,
        "freeze_date": "2026-08-31",
        "providers": ["openai", "anthropic", "vertex"],
        "records": [{"id": "x"}],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_catalog(path, want_major=1)
    assert loaded["catalog_major"] == 1


def test_mismatch_major(tmp_path: Path) -> None:
    payload = {
        "catalog_major": 1,
        "records": [{"id": "x"}],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogError) as exc:
        load_catalog(path, want_major=2)
    assert exc.value.code == "CATALOG_VERSION_MISMATCH"


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogError) as exc:
        load_catalog(tmp_path / "nope.json", want_major=1)
    assert exc.value.code == "CATALOG_LOAD_FAILED"


def test_packaged_catalog_matches_shared_contract() -> None:
    packaged = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "domain"
        / "endpcatalog"
        / "catalog.json"
    )
    shared = (
        Path(__file__).resolve().parents[4]
        / "shared"
        / "contracts"
        / "endpoint-catalog"
        / "v1"
        / "catalog.json"
    )
    assert packaged.is_file()
    assert packaged.read_bytes() == shared.read_bytes()
