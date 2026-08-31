"""Immutable V0.2 product invariants for SF01 contracts."""

from __future__ import annotations

from .endpoint_catalog_lib import build_catalog, validate_catalog
from .helpers import load_text


def test_no_new_api_in_shared_contracts() -> None:
    readme = load_text("shared", "contracts", "README.md").lower()
    assert "new-api" not in readme
    catalog = build_catalog()
    validate_catalog(catalog)
    for rec in catalog["records"]:
        blob = rec["path_template"].lower() + rec["id"].lower()
        assert "new-api" not in blob
        assert "new_api" not in blob


def test_volcano_not_in_v02_catalog() -> None:
    catalog = build_catalog()
    assert "volcano" not in catalog["providers"]
    for rec in catalog["records"]:
        assert rec["provider"] != "volcano"
        assert "volcano" not in rec["path_template"].lower()


def test_provider_connection_has_no_plaintext_readback() -> None:
    text = load_text(
        "shared",
        "contracts",
        "provider-connection",
        "v1",
        "provider-connection.openapi.yaml",
    )
    lowered = text.lower()
    assert "credential_plaintext" not in lowered
    compact = lowered.replace(" ", "")
    assert "writeonly:true" in compact
    assert "credential_fingerprint" in lowered


def test_project_mode_not_patchable() -> None:
    text = load_text("shared", "contracts", "project", "v1", "project.openapi.yaml")
    assert "enum: [shared, dedicated]" in text
    assert "创建后不可变" in text
    assert "MODE_IMMUTABLE" in text
    patch = load_text("shared", "contracts", "project", "v1", "project.openapi.yaml")
    start = patch.find("PatchProjectRequest:")
    assert start > 0
    block = patch[start : start + 400]
    assert "display_name" in block
    assert "mode:" not in block.split("ProtocolState:")[0]


def test_ledger_append_only_and_no_fiat() -> None:
    text = load_text("shared", "contracts", "ledger", "v1", "ledger-entry.schema.json")
    assert "update" not in text.lower() or "additionalProperties" in text
    assert '"delete"' not in text.lower()
    assert "withdraw" not in text.lower()
    assert "recharge" not in text.lower()
    assert "unresolved" in text


def test_usage_unresolved_not_zero() -> None:
    text = load_text(
        "shared", "contracts", "usage", "v1", "usage-observation.schema.json"
    )
    assert "unresolved" in text
    assert "不得把 reported_cost_minor_units 记为 0" in text or "unresolved" in text


def test_route_self_trade_excluded() -> None:
    text = load_text(
        "shared", "contracts", "route-decision", "v1", "route-decision.schema.json"
    )
    assert '"self_trade_excluded"' in text
    assert '"const": true' in text
    assert '"scores"' in text
    assert "1.2.0" in text


def test_dedicated_unavailable_platform_error() -> None:
    text = load_text(
        "shared", "contracts", "native-passthrough", "v1", "platform-errors.md"
    )
    assert "DEDICATED_UNAVAILABLE" in text


def test_no_cross_protocol_conversion_contract() -> None:
    readme = load_text("shared", "contracts", "README.md")
    assert "unified request" not in readme.lower()
    assert "跨协议" not in readme
