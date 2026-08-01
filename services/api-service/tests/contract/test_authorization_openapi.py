"""OpenAPI paths for role-access-isolation align with mounted routes."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[4]
OPENAPI = (
    ROOT
    / "shared"
    / "contracts"
    / "role-access-isolation"
    / "v1"
    / "role-access-isolation.openapi.yaml"
)


def test_contract_paths_present_on_app() -> None:
    doc = yaml.safe_load(OPENAPI.read_text())
    contract_paths = set(doc["paths"].keys())
    # Mounted under /api/v1
    expected = {f"/api/v1{p}" if not p.startswith("/api") else p for p in contract_paths}
    client = TestClient(app)
    live = set(client.app.openapi()["paths"].keys())
    missing = expected - live
    assert not missing, f"routes missing from app OpenAPI: {missing}"


def test_evaluate_operation_declares_security_responses() -> None:
    doc = yaml.safe_load(OPENAPI.read_text())
    eval_op = doc["paths"]["/authorization/evaluate"]["post"]
    codes = set(eval_op["responses"].keys())
    for required in ("200", "401", "403", "404", "503"):
        assert required in codes
