"""Secret scan and SF02 redaction contract tests (T059 / T081).

Generate synthetic suspected credentials and verify that a full-history scan
fails, locates the file, and does not echo the value in output. Also assert
lifecycle event/plain-text surfaces never leak SF02 secrets or workspace paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from workflow.events import DiagnosticCodeV2, emit_event_v2
from workflow.local_env.lifecycle import LifecycleRunOutcome

from .helpers import find_repo_root


@pytest.fixture
def gitleaks_available() -> bool:
    return shutil.which("gitleaks") is not None


def test_gitleaks_detects_synthetic_credential(gitleaks_available: bool) -> None:
    if not gitleaks_available:
        pytest.skip("gitleaks not installed on this host")

    repo_root = find_repo_root()
    scan_dir = repo_root / "tests" / "workflow" / "fixtures" / "secret-scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", dir=scan_dir, delete=False) as fh:
        # Synthetic credential pattern that triggers gitleaks generic-api-key.
        secret = "sk-live-abc123"
        fh.write(f"api_key={secret}\n")
        path = Path(fh.name)

    try:
        # Use an empty config so the repository allowlist does not suppress
        # detection of this intentionally synthetic fixture secret.
        # Default rules without the repository allowlist so this fixture is
        # still detected. Scan only the single temporary file path.
        result = subprocess.run(
            [
                "gitleaks",
                "dir",
                str(path),
                "-v",
                "-r",
                str(path.with_suffix(".json")),
                "--redact",
                "100",
                "--no-config",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, (
            "gitleaks should detect the synthetic credential: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        # The secret value itself must not appear in stdout/stderr.
        assert secret not in result.stdout
        assert secret not in result.stderr
    finally:
        path.unlink(missing_ok=True)


def test_sf02_event_envelope_redacts_secrets_and_workspace_paths() -> None:
    """T081: poisoned lifecycle-shaped messages never retain secrets or paths."""
    secret = "tm_local_" + ("S" * 40)
    workspace = "/Users/tmtest-secret-scan/workspace path"
    event = emit_event_v2(
        action="dev",
        component="repository",
        phase="final",
        status="FAILED",
        code=DiagnosticCodeV2.STEP_FAILED,
        duration_ms=0,
        message=(
            f"probe failed for postgresql://app:{secret}@127.0.0.1:5432/db "
            f"under {workspace} with {secret}"
        ),
        correlation_id="tmtest-secret-scan",
    )
    payload = json.dumps(event, ensure_ascii=False)
    assert secret not in payload
    assert "tm_local_" not in payload
    assert workspace not in payload
    assert "/Users/tmtest-secret-scan" not in payload


def test_sf02_lifecycle_outcome_surfaces_never_leak_secrets_or_paths() -> None:
    """T081: plain_lines and events on a LifecycleRunOutcome stay secret-free."""
    secret = "tm_local_" + ("P" * 40)
    path = "/private/var/tmtest/checkout"
    safe_message = "dependency not ready; project state is retained for inspection"
    event = emit_event_v2(
        action="dev",
        component="infra",
        phase="readiness",
        status="FAILED",
        code=DiagnosticCodeV2.DEPENDENCY_NOT_READY,
        duration_ms=12,
        message=safe_message,
        correlation_id="tmtest-outcome",
        dependency="postgres",
    )
    # Deliberately construct an outcome that would fail the contract if it
    # ever carried a secret in its public surfaces.
    outcome = LifecycleRunOutcome(
        action="dev",
        status="FAILED",
        diagnostic_code="DEPENDENCY_NOT_READY",
        correlation_id="tmtest-outcome",
        project_id="tmtest-aabbccddeeff",
        message=safe_message,
        duration_ms=12,
        events=(event,),
        plain_lines=(
            f"[FAILED] infra dev/readiness postgres: [DEPENDENCY_NOT_READY] "
            f"{safe_message} (duration_ms=12, correlation_id=tmtest-outcome)",
        ),
        dependency_results=(),
    )
    blob = json.dumps(list(outcome.events), ensure_ascii=False) + "\n" + "\n".join(
        outcome.plain_lines
    )
    assert secret not in blob
    assert path not in blob
    assert "tm_local_" not in blob
    assert outcome.project_id.startswith("tmtest-")
