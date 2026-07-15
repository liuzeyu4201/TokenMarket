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
from typing import Any

import pytest

from .helpers import find_repo_root, load_json, repo_path


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


def test_missing_tool_fails_within_five_seconds(
    cli: Any, toolchain_manifest: dict[str, Any], tmp_path: Path
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

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        cli.toolchain_check(manifest_path, repo_root=find_repo_root())
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"toolchain_check took {elapsed:.2f}s, must fail within 5s"
    assert exc_info.value.code == "TOOL_MISSING"
    assert "tm-fake-missing-tool-xyz" in exc_info.value.message


def test_unsupported_version_fails_within_five_seconds(
    cli: Any, toolchain_manifest: dict[str, Any], tmp_path: Path
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

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        cli.toolchain_check(manifest_path, repo_root=find_repo_root())
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

    start = time.monotonic()
    with pytest.raises(cli.WorkflowError) as exc_info:
        cli.toolchain_check(manifest_path, repo_root=find_repo_root())
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"toolchain_check took {elapsed:.2f}s, must fail within 5s"
    assert exc_info.value.code == "CONTRACT_DRIFT"
    assert needle in exc_info.value.message


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
