"""SF02 v2 consumer-migration and activation gate tests (T013).

These tests replace the SF01 transition-only assertions with the explicit
Root Make Workflow v2 gate defined in
``shared/contracts/repository-workflow/v2/make-workflow.md`` (reviewed source:
``specs/002-local-dependency-lifecycle/contracts/make-workflow-v2.md``).

Until every required capability is present — the event v2 envelope emitted,
every enumerated repository-owned event consumer migrated to it, and the
dependency manifest, Compose asset, lifecycle adapter, API/Billing readiness
probes and both-platform evidence complete — the public ``dev``/``dev-down``
targets must keep their stable names and keep failing closed with
``SF02_NOT_READY`` before reading configuration, checking Docker, or mutating
the workspace. The atomic v2 activation is T074; no partial activation and no
dual execution (``SF02_NOT_READY`` plus local resource mutation) is allowed.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from .helpers import find_repo_root, repo_path, run

SF02_CODE = "SF02_NOT_READY"
PUBLIC_TARGETS = ("dev", "dev-down")

# Repository-owned JSONL event readers/fixtures enumerated by T016. An
# unmigrated (still-v1) or missing consumer blocks v2 activation.
V2_EVENT_CONSUMERS = ("helpers.py", "test_events.py", "test_command_contract.py")

# Fields a consumer must understand to read the v2 standard envelope.
V2_ENVELOPE_MARKERS = ("event_id", "correlation_id", "payload")

# Lifecycle adapter modules owned by T014/T017/T026-T031.
LIFECYCLE_MODULES = (
    "models.py",
    "identity.py",
    "config.py",
    "compose.py",
    "probes.py",
    "lifecycle.py",
)

# API/Billing PostgreSQL readiness probe modules owned by T058/T060.
READINESS_PROBE_MODULES = (
    ("services", "api-service", "app", "database.py"),
    ("services", "billing-service", "app", "database.py"),
)

# Both-platform release evidence owned by T069/T070.
PLATFORM_EVIDENCE = ("linux-amd64.md", "macos-arm64.md")


# ---------------------------------------------------------------------------
# v2 activation capability checklist (make-workflow-v2.md migration/activation)
# ---------------------------------------------------------------------------


def _event_emitter_uses_v2_envelope() -> bool:
    """True when workflow.events emits the v2 standard envelope (T015)."""
    try:
        import workflow.events as events_module  # type: ignore[import-not-found]
    except ImportError:
        return False
    event = events_module.emit_event(
        action="dev",
        component="repository",
        phase="preflight",
        status="FAILED",
        code=events_module.DiagnosticCode.SF02_NOT_READY,
        duration_ms=0,
        message="activation gate probe",
        run_id="00000000-0000-0000-0000-000000000000",
    )
    envelope_keys = {
        "event_id",
        "event_type",
        "schema_version",
        "timestamp",
        "producer",
        "correlation_id",
        "payload",
    }
    return (
        envelope_keys <= set(event)
        and event.get("schema_version") == "2.0.0"
        and event.get("event_type") == "workflow.step"
        and event.get("producer") == "repository-workflow"
    )


def _event_consumers_migrated_to_v2() -> bool:
    """True when every enumerated repository consumer reads the v2 envelope (T016)."""
    tests_dir = repo_path("tests", "workflow")
    for name in V2_EVENT_CONSUMERS:
        path = tests_dir / name
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8")
        if not all(marker in text for marker in V2_ENVELOPE_MARKERS):
            return False
    return True


def _dependency_manifest_ready() -> bool:
    """True when the immutable local dependency manifest is committed (T005)."""
    path = repo_path("ops", "workflow", "local-dependencies.json")
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        return False
    digests_ok = all(
        isinstance(dep, dict)
        and isinstance(dep.get("index_digest"), str)
        and dep["index_digest"].startswith("sha256:")
        for dep in dependencies
    )
    ids = [dep.get("id") for dep in dependencies if isinstance(dep, dict)]
    return (
        data.get("schema_version") == "1.0.0"
        and data.get("diagnostic_contract_version") == "2.0.0"
        and ids == ["postgres", "redis", "grafana"]
        and digests_ok
    )


def _compose_asset_present() -> bool:
    """True when the reviewed Compose definition exists (T027)."""
    return repo_path("infra", "docker", "compose.local.yml").is_file()


def _lifecycle_adapter_present() -> bool:
    """True when every lifecycle adapter module exists (T014/T017/T026-T031)."""
    return all(
        repo_path("tools", "workflow", "local_env", module).is_file()
        for module in LIFECYCLE_MODULES
    )


def _readiness_probes_present() -> bool:
    """True when both API and Billing own a PostgreSQL readiness probe (T058/T060)."""
    return all(repo_path(*parts).is_file() for parts in READINESS_PROBE_MODULES)


def _both_platform_evidence_complete() -> bool:
    """True when Linux x86_64 and macOS arm64 lifecycle evidence exist (T069/T070)."""
    evidence_dir = repo_path("specs", "002-local-dependency-lifecycle", "evidence")
    return all((evidence_dir / name).is_file() for name in PLATFORM_EVIDENCE)


def _activation_capabilities() -> dict[str, bool]:
    """Evaluate the v2 activation capability checklist from make-workflow-v2.md."""
    return {
        "event-v2-envelope": _event_emitter_uses_v2_envelope(),
        "event-consumers-migrated": _event_consumers_migrated_to_v2(),
        "dependency-manifest": _dependency_manifest_ready(),
        "compose-asset": _compose_asset_present(),
        "lifecycle-adapter": _lifecycle_adapter_present(),
        "readiness-probes": _readiness_probes_present(),
        "both-platform-evidence": _both_platform_evidence_complete(),
    }


def _activation_gate_open(capabilities: dict[str, bool]) -> bool:
    """The v2 activation gate opens only when every required capability holds."""
    return bool(capabilities) and all(capabilities.values())


@pytest.fixture
def cli() -> Any:
    try:
        import workflow.cli as cli_module  # type: ignore[import-not-found]
    except ImportError as exc:
        pytest.fail(
            f"workflow.cli is unavailable; the SF02 gate cannot be evaluated: {exc}"
        )
    return cli_module


# ---------------------------------------------------------------------------
# Public fail-closed behavior while the gate is closed
# ---------------------------------------------------------------------------


def _root_snapshot() -> set[str]:
    """Return a snapshot of repository-root entries before a side-effect test."""
    root = find_repo_root()
    return {str(p.relative_to(root)) for p in root.iterdir()}


def _run_make(target: str) -> subprocess.CompletedProcess[str]:
    """Invoke a root Make target and capture output."""
    return run(
        ["make", target],
        cwd=find_repo_root(),
        check=False,
    )


def _assert_sf02_block(result: subprocess.CompletedProcess[str], target: str) -> None:
    """Assert that a result represents a clean SF02_NOT_READY failure."""
    output = result.stdout + result.stderr
    assert (
        result.returncode != 0
    ), f"make {target} must fail before SF02; expected non-zero exit, got 0"
    assert SF02_CODE in output, (
        f"make {target} must emit {SF02_CODE}; got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_dev_fails_with_sf02_not_ready() -> None:
    """`make dev` must fail immediately with SF02_NOT_READY."""
    result = _run_make("dev")
    _assert_sf02_block(result, "dev")


def test_dev_down_fails_with_sf02_not_ready() -> None:
    """`make dev-down` must fail immediately with SF02_NOT_READY."""
    result = _run_make("dev-down")
    _assert_sf02_block(result, "dev-down")


def test_dev_does_not_read_configuration() -> None:
    """`make dev` must fail with SF02_NOT_READY before reading real env files."""
    root = find_repo_root()
    allowed = {".env.example", ".env.local.example"}
    for env_file in root.glob(".env*"):
        if env_file.name in allowed or env_file.name.endswith(".example"):
            continue
        # Real .env files must not be present in a fresh checkout; if they are,
        # the workspace has already been mutated and the test cannot prove the
        # pre-config failure order.
        pytest.fail(f"unexpected environment file in repository root: {env_file}")

    result = _run_make("dev")
    _assert_sf02_block(result, "dev")
    assert (
        "INVALID_CONFIG" not in result.stdout + result.stderr
    ), "dev must fail with SF02_NOT_READY before any configuration validation"


def test_dev_does_not_invoke_docker(tmp_path: Path) -> None:
    """`make dev` must fail before any Docker executable is consulted."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text("#!/bin/sh\necho 'FAKE_DOCKER_CALLED' >&2\nexit 99\n")
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

    result = subprocess.run(
        ["make", "dev"],
        cwd=find_repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    _assert_sf02_block(result, "dev")
    assert (
        "FAKE_DOCKER_CALLED" not in result.stdout + result.stderr
    ), "dev must not execute docker before failing with SF02_NOT_READY"


def test_dev_down_has_no_workspace_side_effects() -> None:
    """`make dev-down` must not create, modify or remove repository-root entries."""
    before = _root_snapshot()
    result = _run_make("dev-down")
    after = _root_snapshot()
    _assert_sf02_block(result, "dev-down")
    assert (
        before == after
    ), f"make dev-down changed repository-root entries: {before ^ after}"


@pytest.mark.parametrize("action", PUBLIC_TARGETS)
def test_execute_action_fails_closed_with_sf02_not_ready(
    cli: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    """cli.execute_action keeps public actions on SF02_NOT_READY until T074."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    result = cli.execute_action(action, repo_root=find_repo_root(), plain=False)
    output = capsys.readouterr().out
    assert (
        result != 0
    ), f"execute_action({action!r}) must fail while the v2 gate is closed"
    events = [json.loads(line) for line in output.splitlines() if line.strip()]
    assert events, f"execute_action({action!r}) must emit workflow events"
    codes = {event.get("code") for event in events}
    assert SF02_CODE in codes, f"expected {SF02_CODE} diagnostic, got codes {codes}"
    assert all(
        event.get("status") != "PASSED" for event in events
    ), f"no {action} step may pass while the v2 gate is closed"


# ---------------------------------------------------------------------------
# Stable public surface
# ---------------------------------------------------------------------------


def test_public_target_names_remain_stable() -> None:
    """The v2 change must not rename or remove the public dev/dev-down targets."""
    makefile = repo_path("Makefile").read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^dev dev-down [^\n]+:$", makefile
    ), "root Makefile must keep the stable dev/dev-down target names"
    result = _run_make("help")
    assert result.returncode == 0, "make help must succeed"
    for action in PUBLIC_TARGETS:
        assert (
            f"make {action}" in result.stdout
        ), f"make help must document `make {action}`"


# ---------------------------------------------------------------------------
# v2 consumer-migration and activation gate
# ---------------------------------------------------------------------------


def test_activation_gate_requires_every_capability() -> None:
    """The gate fails closed: any missing capability keeps v2 activation closed."""
    capabilities = _activation_capabilities()
    assert capabilities, "capability checklist must not be empty"
    full = dict.fromkeys(capabilities, True)
    assert _activation_gate_open(
        full
    ), "gate must open only when every capability holds"
    for missing in full:
        partial = dict(full)
        partial[missing] = False
        assert not _activation_gate_open(
            partial
        ), f"missing capability {missing!r} must keep the activation gate closed"
    assert not _activation_gate_open({}), "an empty capability set must fail closed"


def test_consumer_migration_enumeration_is_not_vacuous() -> None:
    """Every consumer the migration gate enumerates must exist on disk."""
    tests_dir = repo_path("tests", "workflow")
    for name in V2_EVENT_CONSUMERS:
        assert (
            tests_dir / name
        ).is_file(), f"enumerated v2 event consumer missing: {name}"


def test_activation_gate_is_currently_closed() -> None:
    """At least one required capability is missing, so the gate stays closed until T074."""
    capabilities = _activation_capabilities()
    missing = [name for name, present in capabilities.items() if not present]
    assert missing and not _activation_gate_open(capabilities), (
        "every v2 activation capability is present; T074 must atomically activate "
        "dev/dev-down, event v2 and help/recovery text in the same change "
        f"(capabilities: {capabilities})"
    )


def test_runtime_behavior_matches_closed_activation_gate(
    cli: Any, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """While the gate is closed, public actions must fail with SF02_NOT_READY."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    capabilities = _activation_capabilities()
    if _activation_gate_open(capabilities):
        pytest.fail(
            "activation gate is open; public v2 activation is atomic in T074 and must "
            "update tools/workflow/cli.py, the Makefile help text and this gate together"
        )
    for action in PUBLIC_TARGETS:
        result = cli.execute_action(action, repo_root=find_repo_root(), plain=False)
        output = capsys.readouterr().out
        assert result != 0, f"{action} must fail while the v2 activation gate is closed"
        assert (
            SF02_CODE in output
        ), f"closed gate requires {action} to fail with {SF02_CODE}; got {output!r}"
