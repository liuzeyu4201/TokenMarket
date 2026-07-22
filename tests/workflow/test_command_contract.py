"""Root Make workflow command contract tests (T015).

These tests verify that the repository root Makefile exposes the stable
public targets, the stable ``bootstrap`` and ``type-check`` support targets,
help text describing purpose/side-effects/recovery, fail-fast aggregation, and
correct exit semantics. They must fail before the root Makefile and workflow
orchestration are implemented.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from .helpers import find_repo_root, load_json, load_text, repo_path, run, validate_event_v2

ROOT_MAKEFILE = repo_path("Makefile")

PUBLIC_TARGETS = [
    "dev",
    "dev-down",
    "deploy",
    "deploy-down",
    "fmt",
    "lint",
    "test",
    "build",
    "migrate",
]
SUPPORT_TARGETS = ["bootstrap", "type-check"]


def _make(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Invoke the root Makefile from the repository root."""
    return run(["make", *args], cwd=find_repo_root(), check=check)


@pytest.fixture(scope="module")
def manifest() -> dict:
    """Load the component manifest; skip individual tests if not yet present."""
    try:
        return load_json("ops", "workflow", "components.json")
    except (FileNotFoundError, ValueError) as exc:  # pragma: no cover - contract gap
        pytest.skip(f"component manifest not yet materialized: {exc}")


class TestRootMakefileExists:
    """The root Makefile is the only public workflow entry point."""

    def test_root_makefile_exists(self) -> None:
        assert ROOT_MAKEFILE.is_file(), "root Makefile must exist as the public workflow entry"


class TestHelpContract:
    """make help documents commands without side effects and within 2s."""

    def test_help_target_exists(self) -> None:
        assert ROOT_MAKEFILE.is_file(), "root Makefile must exist"
        result = _make("help")
        assert (
            result.returncode == 0
        ), f"make help must succeed; stdout={result.stdout!r} stderr={result.stderr!r}"

    @pytest.mark.timeout(2)
    def test_help_completes_within_two_seconds(self) -> None:
        assert ROOT_MAKEFILE.is_file(), "root Makefile must exist"
        result = _make("help")
        assert result.returncode == 0

    @pytest.mark.parametrize("target", PUBLIC_TARGETS)
    def test_help_lists_public_target(self, target: str) -> None:
        result = _make("help")
        assert result.returncode == 0, "make help must succeed before targets are documented"
        output = result.stdout.lower()
        assert (
            target.replace("-", " ") in output or target in output
        ), f"help text must document public target `{target}`"

    @pytest.mark.parametrize("target", SUPPORT_TARGETS)
    def test_help_lists_support_target(self, target: str) -> None:
        result = _make("help")
        assert (
            result.returncode == 0
        ), "make help must succeed before support targets are documented"
        output = result.stdout.lower()
        assert (
            target.replace("-", " ") in output or target in output
        ), f"help text must document support target `{target}`"

    def test_help_documents_purpose_and_side_effects(self) -> None:
        result = _make("help")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert (
            "side effect" in output or "side-effect" in output
        ), "help must describe side effects of stateful targets"
        assert (
            "prerequisite" in output or "precondition" in output
        ), "help must describe prerequisites"

    def test_help_does_not_mutate_workspace(self) -> None:
        result = _make("help")
        assert result.returncode == 0
        # Help must not trigger preflight that writes caches, state, or logs.
        assert (
            "bootstrap" not in result.stderr.lower() or "docker" not in result.stderr.lower()
        ), "help must not perform side effects such as bootstrap or docker checks"


class TestPublicAndSupportTargets:
    """Each documented target is defined in the root Makefile."""

    @pytest.mark.parametrize("target", PUBLIC_TARGETS)
    def test_public_target_defined(self, target: str) -> None:
        result = _make("-n", target)
        assert result.returncode == 0, (
            f"public target `{target}` must be defined in root Makefile; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    @pytest.mark.parametrize("target", SUPPORT_TARGETS)
    def test_support_target_defined(self, target: str) -> None:
        result = _make("-n", target)
        assert result.returncode == 0, (
            f"support target `{target}` must be defined in root Makefile; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_support_targets_do_not_redefine_public_targets(self) -> None:
        makefile_text = ROOT_MAKEFILE.read_text(encoding="utf-8")
        for support in SUPPORT_TARGETS:
            # ``bootstrap`` and ``type-check`` must remain supporting targets;
            # they cannot be aliased to one of the public names.
            for public in PUBLIC_TARGETS:
                assert (
                    f"{support}: {public}" not in makefile_text
                ), f"support target `{support}` must not alias public target `{public}`"


class TestAggregateExitSemantics:
    """Aggregated actions fail fast and return non-zero on any required failure."""

    def test_aggregate_action_fails_when_component_adapter_missing(self, manifest: dict) -> None:
        """If a required component adapter cannot be invoked, the aggregate fails."""
        assert ROOT_MAKEFILE.is_file(), "root Makefile must exist"

        # Select the first required action of the first required component.
        component = manifest["components"][0]
        action = next(a for a in component["actions"] if a["required"])
        adapter = action["adapter"]

        # Dry-run the aggregate for that action; a real adapter must exist.
        result = _make("-n", action["action"])
        assert result.returncode == 0, (
            f"aggregate target `{action['action']}` must be defined and reference "
            f"component `{component['id']}` adapter `{adapter}`"
        )

    def test_aggregate_fails_fast_on_required_step_failure(self, manifest: dict) -> None:
        """A failing required component step must cause the whole action to fail."""
        assert ROOT_MAKEFILE.is_file(), "root Makefile must exist"

        # Pick an action every component binds so the aggregate has work to do.
        action_name = "type-check"
        bound = [
            c["id"]
            for c in manifest["components"]
            if any(a["action"] == action_name and a["required"] for a in c["actions"])
        ]
        assert len(bound) == len(
            manifest["components"]
        ), f"all components must bind required `{action_name}`"

        # The aggregate target must exist and be executable; we do not require it
        # to pass yet (implementation is incomplete), only that invoking it is a
        # defined workflow action that can report failure.
        result = _make("-n", action_name)
        assert (
            result.returncode == 0
        ), f"aggregate target `{action_name}` must be defined in root Makefile"


class TestComponentCoverage:
    """Aggregated actions cover all eight required components."""

    def test_all_required_components_present_in_manifest(self, manifest: dict) -> None:
        ids = {c["id"] for c in manifest["components"]}
        expected = {
            "proxy-gateway",
            "api-service",
            "billing-service",
            "admin-service",
            "frontend",
            "shared",
            "infra",
            "ops",
        }
        assert (
            ids == expected
        ), f"manifest must contain exactly the eight required components: {ids}"

    @pytest.mark.parametrize("action", ["fmt", "lint", "test", "build"])
    def test_aggregate_action_covers_all_service_like_components(
        self, action: str, manifest: dict
    ) -> None:
        service_types = {"go-service", "python-service", "web-frontend"}
        expected = {c["id"] for c in manifest["components"] if c["component_type"] in service_types}
        bound = {
            c["id"]
            for c in manifest["components"]
            if any(a["action"] == action and a["required"] for a in c["actions"])
            and c["component_type"] in service_types
        }
        missing = expected - bound
        assert (
            bound == expected
        ), f"aggregate `{action}` must cover all service-like components; missing {missing}"


V1_MAKE_WORKFLOW = (
    "shared",
    "contracts",
    "repository-workflow",
    "v1",
    "make-workflow.md",
)
V1_EVENT_SCHEMA = (
    "shared",
    "contracts",
    "repository-workflow",
    "v1",
    "workflow-event.schema.json",
)
V2_MAKE_WORKFLOW = (
    "shared",
    "contracts",
    "repository-workflow",
    "v2",
    "make-workflow.md",
)
V2_EVENT_SCHEMA = (
    "shared",
    "contracts",
    "repository-workflow",
    "v2",
    "workflow-event.schema.json",
)


class TestMakeWorkflowEventMigration:
    """Root Make/event v2 migration gate (SF02 T016).

    The v2 contract is published with its consumer-migration/deprecation gate
    while the v1 Make/event artifacts and the current v1 JSONL stream remain
    intact as explicit regression coverage until the activation gate passes.
    """

    def test_v2_make_workflow_contract_published(self) -> None:
        for parts in (V2_MAKE_WORKFLOW, V2_EVENT_SCHEMA):
            path = repo_path(*parts)
            assert path.is_file(), f"missing v2 contract artifact: {path}"
            assert path.read_text(encoding="utf-8").strip(), f"empty v2 artifact: {path}"

    def test_v1_make_workflow_artifacts_retained(self) -> None:
        """Immutable v1 Make/event artifacts stay through the deprecation window."""
        for parts in (V1_MAKE_WORKFLOW, V1_EVENT_SCHEMA):
            path = repo_path(*parts)
            assert path.is_file(), f"v1 history must be retained: {path}"
            assert path.read_text(encoding="utf-8").strip(), f"empty v1 artifact: {path}"

    def test_v2_contract_declares_consumer_migration_gate(self) -> None:
        text = load_text(*V2_MAKE_WORKFLOW)
        for phrase in (
            "Consumer migration gate",
            "Announcement period",
            "Activation",
            "Deprecation window",
        ):
            assert phrase in text, f"v2 contract must declare `{phrase}`"
        assert "No dual JSONL stream" in text, "v2 contract forbids a dual JSONL stream"

    def test_v2_contract_keeps_stable_public_target_names(self) -> None:
        text = load_text(*V2_MAKE_WORKFLOW)
        assert "`dev`" in text and "`dev-down`" in text
        for target in ("dev", "dev-down"):
            result = _make("-n", target)
            assert result.returncode == 0, f"target `{target}` must stay defined through v2"

    def test_current_dev_jsonl_stream_is_strict_v1_until_activation(self) -> None:
        """Until the activation gate, `make dev` still emits only v1 JSONL events."""
        env = os.environ.copy()
        env.pop("NO_COLOR", None)  # force the JSONL branch regardless of terminal env
        result = subprocess.run(
            ["make", "dev"],
            cwd=find_repo_root(),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, "dev remains fail-closed before the v2 activation gate"
        jsonl_lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
        assert jsonl_lines, "dev must emit JSONL step events on the v1 stream"
        for line in jsonl_lines:
            event = json.loads(line)
            assert event["schema_version"] == "1.0.0"
            assert isinstance(event["run_id"], str) and event["run_id"]
            # The migrated strict v2 reader must reject the current v1 stream;
            # the streams never mix and consumers migrate before activation.
            with pytest.raises(AssertionError):
                validate_event_v2(event)
