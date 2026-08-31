"""T018 toolchain preflight and frozen bootstrap tests.

Tests the repository workflow tool's ability to reject missing or unsupported
toolchains and to perform idempotent, frozen dependency preparation. They are
written before the corresponding implementation in `tools/workflow/cli.py`.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

import pytest

from .helpers import find_repo_root, load_json, repo_path

HOSTED_PROFILE = "github-actions-ubuntu-24.04"
HOSTED_ENV = {
    "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux",
    "TOKENMARKET_TOOLCHAIN_PROFILE": HOSTED_PROFILE,
}

# Versions that satisfy the committed local exact_version pins for checked tools.
_LOCAL_OK: dict[str, str] = {
    "go": "1.25.14",
    "python": "3.11.15",
    "node": "24.18.0",
    "npm": "11.16.0",
    "docker": "29.5.3",
}


@pytest.fixture
def cli() -> Any:
    """Import the workflow CLI module that T032 will implement."""
    try:
        import workflow.cli as cli_module  # type: ignore[import]
    except ImportError as exc:
        pytest.fail(f"workflow.cli has not been implemented yet (T032): {exc}")
    return cli_module


@pytest.fixture
def toolchain_manifest() -> dict[str, Any]:
    return load_json("ops", "workflow", "toolchains.json")


def _write_manifest(tmp_path: Path, manifest: dict[str, Any]) -> Path:
    path = tmp_path / "toolchains.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _manifest_copy(toolchain_manifest: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(toolchain_manifest))


def _docker_tool(manifest: dict[str, Any]) -> dict[str, Any]:
    for tool in manifest["tools"]:
        if tool["tool"] == "docker":
            return tool
    pytest.fail("docker tool entry not found in toolchain manifest")


def _patch_versions(
    cli: Any, monkeypatch: pytest.MonkeyPatch, versions: Mapping[str, str | None]
) -> None:
    """Mock version probes so tests do not depend on the host toolchain."""

    def _fake(tool: str) -> str | None:
        if tool in versions:
            return versions[tool]
        # Unlisted tools: treat as missing so a forgotten tool fails loudly.
        return None

    monkeypatch.setattr(cli, "_actual_version", _fake)


def _run_check(
    cli: Any,
    manifest_path: Path,
    *,
    profile: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> None:
    cli.toolchain_check(
        manifest_path,
        repo_root=find_repo_root(),
        profile=profile,
        environment=environment if environment is not None else {},
    )


def test_missing_tool_fails_within_five_seconds(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool declared in the manifest but absent on the host fails fast."""
    manifest = _manifest_copy(toolchain_manifest)
    manifest["tools"].append(
        {
            "tool": "tm-fake-missing-tool-xyz",
            "exact_version": "1.0.0",
            "version_source": "T018 synthetic missing-tool fixture",
            "affected_components": ["repository"],
            "install_policy": "system-managed",
            "integrity_reference": "https://tokenmarket.local/fixtures/missing-tool",
        }
    )
    manifest_path = _write_manifest(tmp_path, manifest)
    _patch_versions(cli, monkeypatch, _LOCAL_OK)

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, manifest_path)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"toolchain_check took {elapsed:.2f}s, must fail within 5s"
    assert exc_info.value.code == "TOOL_MISSING"
    assert "tm-fake-missing-tool-xyz" in exc_info.value.message


def test_unsupported_version_fails_within_five_seconds(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed tool whose actual version does not match the manifest fails fast."""
    manifest = _manifest_copy(toolchain_manifest)
    for tool in manifest["tools"]:
        if tool["tool"] == "python":
            tool["exact_version"] = "99.99.99"
            break
    else:
        pytest.fail("python tool entry not found in toolchain manifest")

    manifest_path = _write_manifest(tmp_path, manifest)
    _patch_versions(cli, monkeypatch, _LOCAL_OK)

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, manifest_path)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"toolchain_check took {elapsed:.2f}s, must fail within 5s"
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"
    assert "python" in exc_info.value.message


@pytest.mark.parametrize(
    "broken_field,broken_value,needle",
    [
        (
            "integrity_reference",
            "services/api-service/uv.lock.does-not-exist",
            "uv.lock.does-not-exist",
        ),
        (
            "integrity_reference",
            "ops/workflow/toolchains.json.does-not-exist",
            "toolchains.json.does-not-exist",
        ),
    ],
    ids=["missing-lockfile-reference", "missing-integrity-file-reference"],
)
def test_missing_lock_or_integrity_reference_fails_within_five_seconds(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    broken_field: str,
    broken_value: str,
    needle: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declared lockfile or integrity reference that does not exist fails fast."""
    manifest = _manifest_copy(toolchain_manifest)
    # Break the first uv-managed tool's file-based integrity reference.
    for tool in manifest["tools"]:
        if tool.get("install_policy") == "uv-managed":
            tool[broken_field] = broken_value
            break
    else:
        pytest.fail("no uv-managed tool entry found in toolchain manifest")

    manifest_path = _write_manifest(tmp_path, manifest)
    _patch_versions(cli, monkeypatch, _LOCAL_OK)

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, manifest_path)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"toolchain_check took {elapsed:.2f}s, must fail within 5s"
    assert exc_info.value.code == "CONTRACT_DRIFT"
    assert needle in exc_info.value.message


def test_local_default_accepts_docker_exact_version(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default profile (unset) accepts Docker 29.5.3 via exact_version."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "29.5.3"})
    _run_check(cli, path, environment={})


def test_local_default_accepts_docker_maintained_prefix(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default profile keeps existing _version_matches prefix for 29.5.*."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "29.5.0"})
    _run_check(cli, path, environment={})


def test_local_default_rejects_docker_28(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default profile rejects GitHub runner Docker 28.0.4."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, path, environment={})
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"
    assert "docker" in exc_info.value.message


@pytest.mark.parametrize(
    "docker_version",
    ["28.0.4", "29.5.3"],
    ids=["runner-28.0.4", "maintained-29.5.3"],
)
def test_hosted_profile_accepts_allowlisted_docker(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    docker_version: str,
) -> None:
    """Hosted profile with GITHUB_ACTIONS proof accepts exact allowlist members."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": docker_version})
    _run_check(
        cli,
        path,
        profile=HOSTED_PROFILE,
        environment=HOSTED_ENV,
    )


@pytest.mark.parametrize(
    "docker_version",
    ["28.0.3", "28.0.5", "29.5.0", "29.6.0", "30.0.0"],
    ids=["28.0.3", "28.0.5", "29.5.0-prefix", "29.6.0", "30.0.0"],
)
def test_hosted_profile_rejects_non_allowlisted_docker(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    docker_version: str,
) -> None:
    """Hosted allowlist is exact-list only; no prefix or range matching."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": docker_version})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            profile=HOSTED_PROFILE,
            environment=HOSTED_ENV,
        )
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"
    assert "docker" in exc_info.value.message


@pytest.mark.parametrize(
    "environment,needle",
    [
        (
            {
                "TOKENMARKET_TOOLCHAIN_PROFILE": HOSTED_PROFILE,
                "RUNNER_OS": "Linux",
            },
            "GITHUB_ACTIONS",
        ),
        (
            {
                "TOKENMARKET_TOOLCHAIN_PROFILE": HOSTED_PROFILE,
                "GITHUB_ACTIONS": "false",
                "RUNNER_OS": "Linux",
            },
            "GITHUB_ACTIONS",
        ),
        (
            {
                "TOKENMARKET_TOOLCHAIN_PROFILE": HOSTED_PROFILE,
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "macOS",
            },
            "RUNNER_OS",
        ),
        (
            {
                "TOKENMARKET_TOOLCHAIN_PROFILE": HOSTED_PROFILE,
                "GITHUB_ACTIONS": "true",
            },
            "RUNNER_OS",
        ),
    ],
    ids=[
        "missing-github-actions",
        "github-actions-false",
        "runner-os-macos",
        "missing-runner-os",
    ],
)
def test_hosted_profile_requires_github_actions_linux_proof(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    needle: str,
) -> None:
    """Hosted profile must not activate without GITHUB_ACTIONS=true and RUNNER_OS=Linux."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, path, environment=environment)
    assert exc_info.value.code == "INVALID_CONFIG"
    assert needle in exc_info.value.message


def test_unknown_toolchain_profile_fails_closed(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, _LOCAL_OK)
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            profile="not-a-real-profile",
            environment={},
        )
    assert exc_info.value.code == "INVALID_CONFIG"
    assert "not-a-real-profile" in exc_info.value.message


def test_docker_missing_is_tool_missing(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": None})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, path, environment={})
    assert exc_info.value.code == "TOOL_MISSING"
    assert "docker" in exc_info.value.message


def test_docker_unparseable_version_does_not_pass(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garbage version tokens must not satisfy exact or allowlist checks."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "not-a-semver"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(cli, path, environment={})
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"
    assert "docker" in exc_info.value.message


def test_go_python_node_version_checks_unchanged(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Language tool pins keep exact/prefix matching independent of Docker profiles."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    for tool_name, bad in (("go", "1.24.0"), ("python", "3.10.0"), ("node", "20.0.0")):
        versions = {**_LOCAL_OK, tool_name: bad}
        _patch_versions(cli, monkeypatch, versions)
        with pytest.raises(cli.WorkflowError) as exc_info:
            _run_check(cli, path, environment={})
        assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"
        assert tool_name in exc_info.value.message


def test_uv_managed_tools_still_skip_host_version_probe(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uv-managed tools are not host-version-checked even if probe returns garbage."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    # Only version-checked tools are patched; black/isort etc. would fail if probed.
    _patch_versions(cli, monkeypatch, _LOCAL_OK)
    _run_check(cli, path, environment={})


def test_cli_profile_arg_overrides_environment(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit profile argument wins over TOKENMARKET_TOOLCHAIN_PROFILE."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    # Env claims hosted, but explicit local must reject 28.0.4.
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            profile="local",
            environment=HOSTED_ENV,
        )
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"


def test_empty_allowed_versions_is_contract_drift(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_copy(toolchain_manifest)
    docker = _docker_tool(manifest)
    docker["execution_overrides"] = {
        HOSTED_PROFILE: {
            "allowed_versions": [],
            "match": "exact-list",
        }
    }
    path = _write_manifest(tmp_path, manifest)
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            profile=HOSTED_PROFILE,
            environment=HOSTED_ENV,
        )
    assert exc_info.value.code == "CONTRACT_DRIFT"
    assert "allowed_versions" in exc_info.value.message


def test_unknown_override_match_is_contract_drift(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_copy(toolchain_manifest)
    docker = _docker_tool(manifest)
    docker["execution_overrides"] = {
        HOSTED_PROFILE: {
            "allowed_versions": ["28.0.4"],
            "match": "semver-range",
        }
    }
    path = _write_manifest(tmp_path, manifest)
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            profile=HOSTED_PROFILE,
            environment=HOSTED_ENV,
        )
    assert exc_info.value.code == "CONTRACT_DRIFT"
    assert "match" in exc_info.value.message


def test_ci_true_alone_does_not_select_hosted_profile(
    cli: Any,
    toolchain_manifest: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI/GITHUB_ACTIONS must not auto-switch profile without explicit profile id."""
    path = _write_manifest(tmp_path, _manifest_copy(toolchain_manifest))
    _patch_versions(cli, monkeypatch, {**_LOCAL_OK, "docker": "28.0.4"})
    with pytest.raises(cli.WorkflowError) as exc_info:
        _run_check(
            cli,
            path,
            environment={
                "CI": "true",
                "GITHUB_ACTIONS": "true",
                "GITHUB_RUN_ID": "12345",
                "RUNNER_OS": "Linux",
            },
        )
    assert exc_info.value.code == "TOOL_VERSION_UNSUPPORTED"


def _copy_for_bootstrap(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(
            ".venv",
            "__pycache__",
            ".pytest_cache",
            "*.pyc",
            ".DS_Store",
        ),
    )


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_bootstrap_is_idempotent(cli: Any, tmp_path: Path) -> None:
    """Two consecutive frozen bootstrap runs must not change locks or resolution."""
    src_component = repo_path("tools", "workflow")
    component = tmp_path / "workflow"
    _copy_for_bootstrap(src_component, component)

    lock = component / "uv.lock"
    assert lock.exists(), "uv.lock must exist for a frozen bootstrap test"
    original_hash = _file_sha256(lock)

    cli.bootstrap(component, frozen=True)
    first_hash = _file_sha256(lock)
    first_resolution = cli.resolve_fingerprint(component)

    cli.bootstrap(component, frozen=True)
    second_hash = _file_sha256(lock)
    second_resolution = cli.resolve_fingerprint(component)

    assert first_hash == original_hash, "frozen bootstrap changed uv.lock on first run"
    assert second_hash == original_hash, "frozen bootstrap changed uv.lock on second run"
    assert first_resolution == second_resolution, "dependency resolution fingerprint drifted"
