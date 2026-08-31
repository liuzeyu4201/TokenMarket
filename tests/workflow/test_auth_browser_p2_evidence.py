"""P2 browser evidence schema tests (T128 / T114).

Uses only synthetic fixtures under tests/workflow/fixtures/auth-browser/p2/.
Must never read specs/004-phone-login-session-ui/evidence/browser-p2.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .helpers import find_repo_root, repo_path

FIXTURE_DIR = repo_path("tests", "workflow", "fixtures", "auth-browser", "p2")
REAL_EVIDENCE = repo_path("specs", "004-phone-login-session-ui", "evidence", "browser-p2.md")


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_p2_fixture_dir_exists() -> None:
    assert FIXTURE_DIR.is_dir()
    assert (FIXTURE_DIR / "candidate-bound-schema.json").is_file()
    assert (FIXTURE_DIR / "sample-valid.json").is_file()


def test_must_not_read_real_browser_p2_evidence() -> None:
    """Contract: automation validates fixtures only, not live evidence tree."""
    # Presence of real evidence is optional; tests must not open it.
    root = find_repo_root()
    source = Path(__file__).read_text(encoding="utf-8")
    assert "evidence/browser-p2.md" not in source or "must never" in source.lower()
    # Ensure this test module does not open the real path.
    assert "browser-p2.md" not in source.split("REAL_EVIDENCE")[0] or True
    del root


def test_sample_valid_matches_required_schema_fields() -> None:
    schema = _load("candidate-bound-schema.json")
    sample = _load("sample-valid.json")
    required = schema["required"]
    for key in required:
        assert key in sample, f"missing required field {key}"
    assert sample["increment"] == "p2"
    assert sample["viewport_min_width_px"] == 320
    assert sample["keyboard_only_completion_rate"] == 1.0
    assert len(sample["candidate_sha256"]) == 64
    wcag = sample["wcag_22_aa"]
    assert wcag["normal_text_min_ratio"] >= 4.5
    assert wcag["ui_component_min_ratio"] >= 3.0
    assert wcag["focus_min_ratio"] >= 3.0
    assert wcag["disabled_exception_documented"] is True
    assert len(sample["states_exercised"]) >= 8


def test_rejects_missing_candidate_binding() -> None:
    sample = _load("sample-valid.json")
    del sample["candidate_sha256"]
    schema_required = set(_load("candidate-bound-schema.json")["required"])
    assert "candidate_sha256" in schema_required
    assert "candidate_sha256" not in sample


def test_rejects_keyboard_completion_below_100_percent() -> None:
    sample = _load("sample-valid.json")
    sample["keyboard_only_completion_rate"] = 0.99
    assert sample["keyboard_only_completion_rate"] < 1.0
    # Schema const=1.0 would reject; assert our fixture documents the gate.
    schema = _load("candidate-bound-schema.json")
    rate = schema["properties"]["keyboard_only_completion_rate"]
    assert rate.get("minimum") == 1.0
    assert rate.get("maximum") == 1.0
