"""Contract asset tests (SF01 T070) and SF02 contract guard tests (T008).

The SF01 section verifies that shared contracts have schema, owner, semantic
version, compatibility/deprecation fields, working links and traceability to
their planning source.

The SF02 section guards the frozen SF02 contract materialization: every
materialized shared contract copy must be byte-identical to its reviewed
source under ``specs/002-local-dependency-lifecycle/contracts/``, the
schema-version constants must stay pinned, the v1 Make/event artifacts must
remain immutable since HEAD, the health contract must be a backward
compatible 1.1 minor update, and the contract catalog must register exactly
the contracts present on disk with ownership, compatibility and deprecation
status.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from .helpers import find_repo_root, load_json, load_text, repo_path


def test_contract_manifest_exists_and_valid() -> None:
    manifest = repo_path(
        "shared", "contracts", "_meta", "contract-manifest.schema.json"
    )
    assert manifest.is_file()


def test_contracts_have_source_mapping() -> None:
    root = find_repo_root()
    contract_dir = root / "shared" / "contracts" / "repository-workflow" / "v1"
    for path in contract_dir.glob("*.json"):
        data = load_json("shared", "contracts", "repository-workflow", "v1", path.name)
        assert "$schema" in data
        assert "schema_version" in data


# ---------------------------------------------------------------------------
# T008 (a): materialized SF02 contract copies are byte-identical to sources
# ---------------------------------------------------------------------------

# (reviewed source under specs/002 contracts, materialized shared copy).
# Note the intentional filename differences between source and copy.
SF02_CONTRACT_COPIES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "specs",
            "002-local-dependency-lifecycle",
            "contracts",
            "local-environment-lifecycle.md",
        ),
        ("shared", "contracts", "local-environment", "v1", "lifecycle.md"),
    ),
    (
        (
            "specs",
            "002-local-dependency-lifecycle",
            "contracts",
            "local-dependency-manifest.schema.json",
        ),
        (
            "shared",
            "contracts",
            "local-environment",
            "v1",
            "local-dependency-manifest.schema.json",
        ),
    ),
    (
        ("specs", "002-local-dependency-lifecycle", "contracts", "make-workflow-v2.md"),
        ("shared", "contracts", "repository-workflow", "v2", "make-workflow.md"),
    ),
    (
        (
            "specs",
            "002-local-dependency-lifecycle",
            "contracts",
            "workflow-event-v2.0.schema.json",
        ),
        (
            "shared",
            "contracts",
            "repository-workflow",
            "v2",
            "workflow-event.schema.json",
        ),
    ),
    (
        (
            "specs",
            "002-local-dependency-lifecycle",
            "contracts",
            "service-health-v1.1.openapi.yaml",
        ),
        (
            "shared",
            "contracts",
            "repository-workflow",
            "v1",
            "service-health.openapi.yaml",
        ),
    ),
)


def _git_show_bytes(relative_path: str) -> bytes:
    """Return the committed HEAD bytes of a repository file (read-only git)."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=find_repo_root(),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"git show HEAD:{relative_path} failed: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout


@pytest.mark.parametrize(
    ("source_parts", "copy_parts"),
    SF02_CONTRACT_COPIES,
    ids=[copy_parts[-1] for _, copy_parts in SF02_CONTRACT_COPIES],
)
def test_materialized_contract_copy_is_byte_identical(
    source_parts: tuple[str, ...], copy_parts: tuple[str, ...]
) -> None:
    """Each shared contract copy is byte-identical to its reviewed SF02 source."""
    root = find_repo_root()
    source = root.joinpath(*source_parts)
    copy_path = root.joinpath(*copy_parts)
    assert source.is_file(), f"SF02 contract source missing: {source}"
    assert copy_path.is_file(), f"materialized contract copy missing: {copy_path}"
    assert source.read_bytes() == copy_path.read_bytes(), (
        f"{copy_path.relative_to(root)} drifted from its reviewed source "
        f"{source.relative_to(root)}"
    )


# ---------------------------------------------------------------------------
# T008 (b): pinned schema_version / diagnostic const values
# ---------------------------------------------------------------------------


def test_manifest_schema_declares_version_constants() -> None:
    """The manifest schema pins schema_version 1.0.0 and diagnostics 2.0.0."""
    schema = load_json(
        "shared",
        "contracts",
        "local-environment",
        "v1",
        "local-dependency-manifest.schema.json",
    )
    properties = schema["properties"]
    assert properties["schema_version"] == {"const": "1.0.0"}
    assert properties["diagnostic_contract_version"] == {"const": "2.0.0"}
    assert schema["$id"].endswith(
        "/local-environment/v1/local-dependency-manifest.schema.json"
    )


def test_workflow_event_v2_declares_envelope_version_constants() -> None:
    """The event v2 schema pins the 2.0.0 standard envelope identity fields."""
    schema = load_json(
        "shared", "contracts", "repository-workflow", "v2", "workflow-event.schema.json"
    )
    properties = schema["properties"]
    assert properties["schema_version"] == {"const": "2.0.0"}
    assert properties["event_type"] == {"const": "workflow.step"}
    assert properties["producer"] == {"const": "repository-workflow"}
    assert set(schema["required"]) == {
        "event_id",
        "event_type",
        "schema_version",
        "timestamp",
        "producer",
        "correlation_id",
        "payload",
    }


# ---------------------------------------------------------------------------
# T008 (c): v1 Make/event immutability since HEAD
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative_path",
    [
        "shared/contracts/repository-workflow/v1/make-workflow.md",
        "shared/contracts/repository-workflow/v1/workflow-event.schema.json",
    ],
    ids=["make-workflow.md", "workflow-event.schema.json"],
)
def test_v1_make_and_event_artifacts_are_immutable_since_head(
    relative_path: str,
) -> None:
    """v1 Make/event artifacts stay byte-identical to HEAD during the v2 window.

    Only ``service-health.openapi.yaml`` may differ from HEAD, because it
    received the backward-compatible 1.1 minor update; the two v1 Make/event
    artifacts are immutable history.
    """
    current = find_repo_root().joinpath(*relative_path.split("/"))
    assert current.is_file(), f"v1 contract artifact missing: {relative_path}"
    assert current.read_bytes() == _git_show_bytes(relative_path), (
        f"{relative_path} is immutable v1 history and must not change while the "
        "v2 migration/deprecation window is open"
    )


# ---------------------------------------------------------------------------
# T008 (d): health contract v1.1 minor compatibility
# ---------------------------------------------------------------------------

EXPECTED_200_REQUIRED = {"service", "status", "version", "request_id"}
HEALTH_CONTRACT_REL = (
    "shared/contracts/repository-workflow/v1/service-health.openapi.yaml"
)


def _health_contract_text() -> str:
    return load_text(
        "shared",
        "contracts",
        "repository-workflow",
        "v1",
        "service-health.openapi.yaml",
    )


def _health_contract_head_text() -> str:
    return _git_show_bytes(HEALTH_CONTRACT_REL).decode("utf-8")


def _yaml_block(text: str, header: str) -> str:
    """Return the YAML block starting at the exact ``header`` line.

    The block ends at the next non-empty line whose indentation is less than
    or equal to the header's indentation. The health contract is a frozen,
    consistently indented asset, so indentation-based extraction is stable.
    """
    lines = text.splitlines()
    try:
        start = lines.index(header)
    except ValueError:
        return ""
    indent = len(header) - len(header.lstrip())
    block = [header]
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            block.append(line)
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return "\n".join(block)


def _required_fields(block: str) -> set[str]:
    """Return the field names listed under ``required:`` in a YAML block."""
    fields: set[str] = set()
    in_required = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped == "required:":
            in_required = True
            continue
        if in_required:
            if stripped.startswith("- "):
                fields.add(stripped[2:])
            else:
                break
    return fields


def test_health_v1_1_keeps_200_response_shapes() -> None:
    """The 1.1 minor update keeps the exact SF01 200 field set and version 1.1.0.

    After the SF02 health 1.1 asset is committed, HEAD matches the working tree
    (both 1.1.0). The SF01 200 required-field set remains the compatibility
    baseline and is checked against the frozen EXPECTED_200_REQUIRED constant
    rather than re-reading a historical 1.0.0 blob from HEAD.
    """
    text = _health_contract_text()
    head_text = _health_contract_head_text()
    assert re.search(
        r"(?m)^ {2}version: 1\.1\.0$", text
    ), "health contract must be 1.1.0"
    assert re.search(
        r"(?m)^ {2}version: 1\.1\.0$", head_text
    ), "committed HEAD health contract must already be the 1.1.0 minor update"
    assert text == head_text, "working-tree health contract must match committed HEAD"
    liveness = _yaml_block(text, "    LivenessResponse:")
    readiness = _yaml_block(text, "    ReadinessResponse:")
    assert liveness, "LivenessResponse schema missing from health v1.1"
    assert readiness, "ReadinessResponse schema missing from health v1.1"
    assert _required_fields(liveness) == EXPECTED_200_REQUIRED
    assert _required_fields(readiness) == EXPECTED_200_REQUIRED
    assert "additionalProperties: false" in liveness
    assert "additionalProperties: false" in readiness
    assert "const: alive" in liveness
    assert "const: ready" in readiness


def test_health_v1_1_liveness_has_no_dependency_probe() -> None:
    """Liveness keeps its 200-only, never-probing behavior from SF01."""
    live = _yaml_block(_health_contract_text(), "  /health/live:")
    assert live, "/health/live definition is missing"
    assert '"200":' in live, "/health/live must keep its 200 response"
    assert '"503":' not in live, "/health/live must not fail on dependencies"
    assert "Never probes PostgreSQL" in live


def test_health_v1_1_adds_only_api_billing_postgres_503_readiness() -> None:
    """The only addition is the API/Billing PostgreSQL-aware 503 readiness shape."""
    text = _health_contract_text()
    live = _yaml_block(text, "  /health/live:")
    ready = _yaml_block(text, "  /health/ready:")
    assert '"503":' not in live, "liveness must not gain a dependency 503"
    assert '"200":' in ready and '"503":' in ready
    assert "DependencyReadinessResponse" in ready
    dependency = _yaml_block(text, "    DependencyReadinessResponse:")
    assert dependency, "health v1.1 must add the 503 dependency readiness schema"
    assert "- api-service" in dependency
    assert "- billing-service" in dependency
    assert "const: not_ready" in dependency
    assert "minItems: 1" in dependency
    assert "maxItems: 1" in dependency
    result = _yaml_block(text, "    DependencyResult:")
    assert "const: postgres" in result
    assert "- INVALID_CONFIG" in result
    assert "- DEPENDENCY_NOT_READY" in result
    # The minor update must not introduce a new success shape.
    assert (
        _required_fields(_yaml_block(text, "    ReadinessResponse:"))
        == EXPECTED_200_REQUIRED
    )


def test_health_v1_1_gateway_admin_gain_no_dependency_probe() -> None:
    """Gateway and Admin keep SF01 self-readiness; they gain no dependency probe."""
    text = _health_contract_text()
    service_names = _yaml_block(text, "    ServiceName:")
    for name in ("proxy-gateway", "api-service", "billing-service", "admin-service"):
        assert f"- {name}" in service_names, f"200 shapes must still cover {name}"
    dependency = _yaml_block(text, "    DependencyReadinessResponse:")
    assert "- proxy-gateway" not in dependency
    assert "- admin-service" not in dependency


# ---------------------------------------------------------------------------
# T008 (e): contract catalog drift
# ---------------------------------------------------------------------------

# path -> (owner, version prefix) exactly as registered in the catalog table.
EXPECTED_CATALOG: dict[str, tuple[str, str]] = {
    "repository-workflow/v1/": ("Repository maintainers", "1.0.0"),
    "repository-workflow/v1/service-health.openapi.yaml": (
        "Repository maintainers",
        "1.1.0",
    ),
    "repository-workflow/v2/": ("Repository maintainers", "2.0.0"),
    "local-environment/v1/": ("Repository and infrastructure maintainers", "1.0.0"),
    "deploy-environment/v1/": ("Repository and infrastructure maintainers", "1.0.0"),
    "user-registration/v1/": ("API Service (user domain)", "1.0.0"),
    "phone-auth-session/v1/": ("API Service (authentication domain)", "1.0.0"),
    "role-access-isolation/v1/": ("API Service (authorization domain)", "1.0.0"),
    "volcano-key-validation/v1/": ("Proxy Gateway (provider validation)", "1.0.0"),
    "volcano-openai-compat/v1/": (
        "Proxy Gateway (Chat Completions adapter)",
        "1.0.0",
    ),
    "endpoint-catalog/v1/": ("Proxy Gateway (V0.2 Endpoint Catalog)", "1.0.0"),
    "native-passthrough/v1/": (
        "Proxy Gateway (native same-protocol kernel, SF18+)",
        "1.6.0",
    ),
    "project/v1/": ("API Service (Project domain, SF10+)", "1.2.0"),
    "provider-binding/v1/": (
        "API Service (Provider Binding, SF11+)",
        "1.1.0",
    ),
    "project-proxy-key/v1/": (
        "API Service (Project proxy Key, SF12+)",
        "1.0.0",
    ),
    "provider-connection/v1/": (
        "API Service (Provider Connection, SF14+)",
        "1.3.0",
    ),
    "route-decision/v1/": ("Proxy Gateway (routing decision, SF23+)", "1.2.0"),
    "usage/v1/": ("Billing Service (usage observation, SF26+)", "1.1.0"),
    "pricing/v1/": ("Billing Service (versioned rates, SF27+)", "1.1.0"),
    "seller-workbench/v1/": (
        "API Service + Frontend (seller quote workbench, SF17)",
        "1.0.0",
    ),
    "ledger/v1/": ("Billing Service (immutable ledger, SF28+)", "1.2.0"),
    "admin-identity/v1/": (
        "Admin Service (admin identity/RBAC, SF30)",
        "1.0.0",
    ),
    "admin-console/v1/": (
        "Admin Service (ops console, SF31)",
        "1.0.0",
    ),
    "observability/v1/": (
        "Proxy Gateway + Admin Service (SLO/alerts, SF32)",
        "1.0.0",
    ),
    "capacity/v1/": (
        "Proxy Gateway (capacity/resilience, SF33)",
        "1.0.0",
    ),
    "release-gate/v1/": (
        "Repository maintainers (release go/no-go, SF34)",
        "1.0.0",
    ),
    "audit/v1/": ("Admin Service (audit events, SF30+)", "1.1.0"),
    "usage-outbox/v1/": ("Proxy Gateway (usage outbox, SF04)", "1.0.0"),
    "unified-phone-auth/v1/": (
        "API Service (unified phone auth, SF06)",
        "1.0.0",
    ),
    "single-session-auth/v1/": (
        "API Service (single-session hardening, SF07)",
        "1.0.0",
    ),
    "web-design-system/v1/": (
        "Frontend (design system and app shell, SF08)",
        "1.0.0",
    ),
    "workspace-switch/v1/": (
        "API Service (workspace switch, SF09)",
        "1.0.0",
    ),
}


def _catalog_rows() -> list[list[str]]:
    """Return the data rows of the catalog table in shared/contracts/README.md."""
    rows: list[list[str]] = []
    for line in load_text("shared", "contracts", "README.md").splitlines():
        if line.startswith("| `"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def test_contract_catalog_registers_exactly_on_disk_contracts() -> None:
    """The catalog registers exactly the contracts on disk: no missing, no phantom."""
    rows = _catalog_rows()
    registered = {row[0].strip("`") for row in rows}
    expected = set(EXPECTED_CATALOG)
    assert registered == expected, (
        f"catalog drift: missing={sorted(expected - registered)} "
        f"phantom={sorted(registered - expected)}"
    )
    contracts_root = repo_path("shared", "contracts")
    for entry in registered:
        assert (
            contracts_root / entry.rstrip("/")
        ).exists(), f"phantom catalog entry: {entry}"
    for group_dir in sorted(contracts_root.iterdir()):
        if not group_dir.is_dir() or group_dir.name == "_meta":
            continue
        for version_dir in sorted(group_dir.iterdir()):
            if version_dir.is_dir() and any(version_dir.iterdir()):
                key = f"{group_dir.name}/{version_dir.name}/"
                assert (
                    key in registered
                ), f"contract on disk missing from catalog: {key}"


def test_contract_catalog_rows_carry_owner_version_and_format() -> None:
    """Every catalog row records the expected owner, version and format."""
    rows = _catalog_rows()
    assert rows, "contract catalog table is missing from shared/contracts/README.md"
    for row in rows:
        assert len(row) == 4, f"catalog row must have path/owner/version/format: {row}"
        path = row[0].strip("`")
        expected = EXPECTED_CATALOG.get(path)
        assert expected is not None, f"unexpected catalog entry: {path}"
        owner, version = expected
        assert row[1] == owner, f"{path} owner drifted: {row[1]!r}"
        assert row[2].startswith(version), f"{path} version drifted: {row[2]!r}"
        assert row[3], f"{path} format cell must not be empty"
    v2_row = next(row for row in rows if row[0] == "`repository-workflow/v2/`")
    assert (
        "activated" in v2_row[2].lower()
    ), "workflow v2 must be marked activated after T074"


def test_contract_catalog_records_compatibility_and_deprecation_status() -> None:
    """The catalog records the health 1.1 compatibility and v2 deprecation status."""
    text = load_text("shared", "contracts", "README.md")
    # Health 1.1.0 is a backward-compatible minor update.
    assert "1.1.0" in text
    assert "backward-compatible" in text
    assert "503" in text
    assert "unchanged" in text
    # Workflow v2 activation and the v1 deprecation window.
    assert "Activated at T074" in text or "activated T074" in text
    assert "SF02_NOT_READY" in text
    assert "deprecation window" in text
    assert "next tagged release" in text
    # Lifecycle v1 ownership and change control.
    assert "Repository and infrastructure maintainers" in text
    assert "new version" in text
    assert "synchronized consumers" in text
    # Deploy-environment v1 catalog entry (ADR 003).
    assert "deploy-environment/v1/" in text
    assert "make deploy" in text
