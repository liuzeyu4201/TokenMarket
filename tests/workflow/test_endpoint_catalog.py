"""SF01 Endpoint Catalog validation, coverage, and deterministic listing."""

from __future__ import annotations

import copy
import json

from .endpoint_catalog_lib import (CATALOG_MAJOR, REQUIRED, CatalogError,
                                   build_catalog, dump_catalog,
                                   render_markdown, validate_catalog)
from .helpers import find_repo_root


def _catalog() -> dict:
    catalog = build_catalog()
    validate_catalog(catalog)
    return catalog


def test_unique_keys_and_ids() -> None:
    catalog = _catalog()
    keys = [
        (r["provider"], r["protocol_version"], r["method"], r["path_template"])
        for r in catalog["records"]
    ]
    assert len(keys) == len(set(keys))
    ids = [r["id"] for r in catalog["records"]]
    assert len(ids) == len(set(ids))


def test_three_vendor_stable_families_covered() -> None:
    catalog = _catalog()
    paths = {
        (r["provider"], r["method"], r["path_template"], r["stability"])
        for r in catalog["records"]
    }
    assert ("openai", "POST", "/v1/chat/completions", "stable") in paths
    assert ("openai", "POST", "/v1/responses", "stable") in paths
    assert ("openai", "POST", "/v1/files", "stable") in paths
    assert ("openai", "WEBSOCKET", "/v1/realtime", "stable") in paths
    assert ("openai", "POST", "/v1/embeddings", "stable") in paths
    assert ("openai", "POST", "/v1/batches", "stable") in paths
    assert ("openai", "POST", "/v1/fine_tuning/jobs", "stable") in paths
    assert ("openai", "POST", "/v1/vector_stores", "stable") in paths
    assert ("anthropic", "POST", "/v1/messages", "stable") in paths
    assert ("anthropic", "POST", "/v1/messages/count_tokens", "stable") in paths
    assert ("anthropic", "POST", "/v1/messages/batches", "stable") in paths
    assert (
        "vertex",
        "POST",
        "/v1/projects/{project}/locations/{location}/publishers/"
        "{publisher}/models/{model}:generateContent",
        "stable",
    ) in paths
    assert (
        "vertex",
        "POST",
        "/v1/projects/{project}/locations/{location}/publishers/"
        "{publisher}/models/{model}:streamGenerateContent",
        "stable",
    ) in paths
    assert (
        "vertex",
        "POST",
        "/v1/projects/{project}/locations/{location}/batchPredictionJobs",
        "stable",
    ) in paths
    stables = [r for r in catalog["records"] if r["stability"] == "stable"]
    assert {r["provider"] for r in stables} == {"openai", "anthropic", "vertex"}


def test_stable_records_have_traceability() -> None:
    catalog = _catalog()
    for rec in catalog["records"]:
        if rec["stability"] != "stable":
            continue
        assert rec["official_source"]
        assert rec["test_fixture_version"]
        assert rec["owning_sf"].startswith("SF")


def test_missing_required_fields_rejected() -> None:
    catalog = _catalog()
    rec = copy.deepcopy(catalog["records"][0])
    for field in (
        "stability",
        "stateful",
        "transport",
        "metering_source",
        "test_fixture_version",
    ):
        broken = copy.deepcopy(catalog)
        broken["records"][0] = copy.deepcopy(rec)
        del broken["records"][0][field]
        try:
            validate_catalog(broken)
        except CatalogError:
            continue
        raise AssertionError(f"expected reject missing {field}")


def test_illegal_stability_rejected() -> None:
    catalog = _catalog()
    catalog["records"][0]["stability"] = "experimental"
    try:
        validate_catalog(catalog)
    except CatalogError:
        return
    raise AssertionError("expected reject")


def test_duplicate_key_rejected() -> None:
    catalog = _catalog()
    catalog["records"].append(copy.deepcopy(catalog["records"][0]))
    catalog["records"][-1]["id"] = catalog["records"][-1]["id"] + ".dup"
    try:
        validate_catalog(catalog)
    except CatalogError:
        return
    raise AssertionError("expected duplicate reject")


def test_preview_requires_opt_in() -> None:
    catalog = _catalog()
    preview = next(
        r for r in catalog["records"] if r["stability"] in {"preview", "beta"}
    )
    preview["requires_project_opt_in"] = False
    try:
        validate_catalog(catalog)
    except CatalogError:
        return
    raise AssertionError("expected opt-in reject")


def test_control_plane_and_preview_exist() -> None:
    catalog = _catalog()
    st = {r["stability"] for r in catalog["records"]}
    assert "control_plane" in st
    assert "preview" in st or "beta" in st


def test_catalog_markdown_deterministic() -> None:
    catalog = _catalog()
    a = render_markdown(catalog)
    b = render_markdown(catalog)
    assert a == b
    dumped = dump_catalog(catalog)
    assert dumped == dump_catalog(json.loads(dumped))


def test_committed_catalog_matches_generator() -> None:
    catalog = _catalog()
    expected = dump_catalog(catalog)
    committed = (
        find_repo_root() / "shared/contracts/endpoint-catalog/v1/catalog.json"
    ).read_text(encoding="utf-8")
    assert committed == expected
    listing = render_markdown(catalog)
    md = (
        find_repo_root() / "shared/contracts/endpoint-catalog/v1/CATALOG.md"
    ).read_text(encoding="utf-8")
    assert md == listing


def test_snapshot_and_spec_copies_byte_identical() -> None:
    root = find_repo_root()
    src = (root / "shared/contracts/endpoint-catalog/v1/catalog.json").read_bytes()
    spec = (
        root / "specs/020-endpoint-catalog-governance/contracts/catalog.json"
    ).read_bytes()
    snap = (
        root
        / "services/proxy-gateway/internal/domain/endpcatalog/catalog.snapshot.json"
    ).read_bytes()
    assert src == spec == snap
    schema_src = (
        root / "specs/020-endpoint-catalog-governance/contracts/catalog.schema.json"
    ).read_bytes()
    schema_shared = (
        root / "shared/contracts/endpoint-catalog/v1/catalog.schema.json"
    ).read_bytes()
    assert schema_src == schema_shared


def test_catalog_major_is_v1() -> None:
    assert _catalog()["catalog_major"] == CATALOG_MAJOR == 1
    for rec in _catalog()["records"]:
        for field in REQUIRED:
            assert field in rec


CONTRACT_COPIES = (
    ("catalog.schema.json", "endpoint-catalog"),
    ("platform-errors.md", "endpoint-catalog"),
    ("compatibility.md", "endpoint-catalog"),
    ("freeze-record.md", "endpoint-catalog"),
    ("project.openapi.yaml", "project"),
    ("provider-connection.openapi.yaml", "provider-connection"),
    ("route-decision.schema.json", "route-decision"),
    ("usage-observation.schema.json", "usage"),
    ("pricing.schema.json", "pricing"),
    ("ledger-entry.schema.json", "ledger"),
    ("audit-event.schema.json", "audit"),
)


def test_spec_contracts_materialized_byte_identical() -> None:
    root = find_repo_root()
    src_root = root / "specs" / "020-endpoint-catalog-governance" / "contracts"
    for filename, group in CONTRACT_COPIES:
        src = (src_root / filename).read_bytes()
        dest = (root / "shared" / "contracts" / group / "v1" / filename).read_bytes()
        assert src == dest, filename
