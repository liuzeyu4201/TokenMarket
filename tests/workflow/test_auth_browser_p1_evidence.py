"""P1 browser evidence schema tests (T040).

Uses only synthetic fixtures under tests/workflow/fixtures/auth-browser/p1/.
Must never read specs/004-phone-login-session-ui/evidence/browser-p1.md.
"""

from __future__ import annotations

import json

from .helpers import repo_path

FIXTURE_DIR = repo_path("tests", "workflow", "fixtures", "auth-browser", "p1")


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_p1_fixture_dir_exists() -> None:
    assert FIXTURE_DIR.is_dir()
    assert (FIXTURE_DIR / "candidate-bound-schema.json").is_file()
    assert (FIXTURE_DIR / "sample-valid.json").is_file()


def test_module_loads_only_workflow_fixtures() -> None:
    """All sample data comes from tests/workflow/fixtures/auth-browser/p1/."""
    assert "tests/workflow/fixtures/auth-browser/p1" in str(FIXTURE_DIR)
    assert FIXTURE_DIR.is_relative_to(repo_path("tests", "workflow", "fixtures"))


def test_sample_valid_binds_candidate_and_thresholds() -> None:
    schema = _load("candidate-bound-schema.json")
    sample = _load("sample-valid.json")
    for key in schema["required"]:
        assert key in sample
    assert sample["increment"] == "p1"
    assert sample["cold_start_samples"] == 20
    assert sample["journey_samples"] == 20
    assert sample["cold_start_p95_ms"] <= 3000
    assert sample["journey_max_ms"] <= 180_000
    assert sample["protected_content_flash"] is False
    assert sample["cookie_csrf_persisted"] is False
    assert sample["privacy_sentinel_hits"] == 0
    assert len(sample["candidate_sha256"]) == 64
    assert sample["resources"]["cpu_vcpus"] >= 1


def test_schema_forbids_dropping_outliers() -> None:
    schema = _load("candidate-bound-schema.json")
    outlier = schema["properties"]["outliers"]["items"]
    assert outlier["properties"]["retained"]["const"] is True
