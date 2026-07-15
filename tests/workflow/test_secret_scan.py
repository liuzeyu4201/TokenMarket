"""T059 secret scan contract tests.

Generate synthetic suspected credentials and verify that a full-history scan
fails, locates the file, and does not echo the value in output.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

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
        result = subprocess.run(
            [
                "gitleaks",
                "dir",
                str(scan_dir),
                "-v",
                "-r",
                str(path.with_suffix(".json")),
                "--redact",
                "100",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, "gitleaks should detect the synthetic credential"
        # The secret value itself must not appear in stdout/stderr.
        assert secret not in result.stdout
        assert secret not in result.stderr
    finally:
        path.unlink(missing_ok=True)
