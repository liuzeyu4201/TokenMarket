"""Security helpers: redaction and configuration metadata validation.

This module provides the minimum redaction and placeholder validation used by
``events.py`` and ``cli.py`` in SF01. The full configuration contract tests are
implemented in US2.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(
        r"([a-zA-Z0-9_-]*(?:api[_-]?key|apikey|secret|token|password)"
        r"[\s]*[=:\s][\s]*)([^\s\"']{8,})",
        re.IGNORECASE,
    ),
    re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]{8,})", re.IGNORECASE),
]


def redact(message: str) -> str:
    """Redact secret-like values from a string while keeping variable names."""
    message = _SECRET_PATTERNS[0].sub("[REDACTED]", message)
    message = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", message)
    message = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", message)
    return message


def is_safe_placeholder(value: str) -> bool:
    """Return True if a value looks like a synthetic unusable placeholder."""
    if not value:
        return False
    lowered = value.lower()
    return (
        (value.startswith("<") and value.endswith(">"))
        or "replace" in lowered
        or "changeme" in lowered
        or "example" in lowered
        or "placeholder" in lowered
    )


def validate_no_secret_in_text(text: str, context: str = "text") -> None:
    """Raise if the text appears to contain a real credential."""
    # First check whether the whole text is a safe placeholder; if so allow it.
    if is_safe_placeholder(text.strip()):
        return
    # Split on key/value separators and check values only.
    for line in text.splitlines():
        for sep in ("=", ":"):
            if sep in line:
                _, _, value = line.partition(sep)
                value = value.strip().strip("\"'")
                if value and is_safe_placeholder(value):
                    continue
                for pattern in _SECRET_PATTERNS:
                    if pattern.search(line):
                        raise ValueError(f"possible secret detected in {context}")
                break


def load_env_example(path: Any) -> dict[str, str]:
    """Parse a .env.example-style file into name/value entries."""
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                name, _, value = line.partition("=")
                result[name.strip()] = value.strip()
    return result


def validate_config(schema: dict[str, Any], values: dict[str, str]) -> None:
    """Validate configuration values against a metadata schema.

    Raises ``ValueError`` before any persistent side effect. Error messages
    expose only variable names, never values.
    """
    for name, meta in schema.items():
        required = meta.get("required", False)
        value = values.get(name)

        if required and not value:
            raise ValueError(f"configuration variable {name!r} is required but missing or empty")

        if not value:
            continue

        expected_type = meta.get("type")
        if expected_type == "integer":
            try:
                int(value)
            except ValueError as exc:
                raise ValueError(f"configuration variable {name!r} must be an integer") from exc
        elif expected_type == "string":
            pass

        allowed = meta.get("allowed")
        if allowed and value not in allowed:
            raise ValueError(f"configuration variable {name!r} has an unsupported value")

        dangerous_defaults = meta.get("dangerous_defaults", [])
        if value in dangerous_defaults:
            raise ValueError(f"configuration variable {name!r} uses a dangerous default value")


def run_security_checks(repo_root: Any, *, max_retries: int = 1) -> None:
    """Run fail-closed security scans with bounded retries.

    Scans cover Git history (gitleaks), Go vulnerabilities (govulncheck),
    Python lock files (pip-audit) and npm dependencies (npm audit). Any
    required scanner that is missing or reports findings raises an error.

    Authentication feature (004) additionally validates reviewed dev-dependency
    pins/licenses via ``dependency_policy`` before external scanners run.
    """
    import os
    import shutil
    import subprocess
    import tempfile

    repo_root = Path(repo_root)

    # Fail closed on unpinned or disallowed auth dev dependencies (004 T007).
    from .dependency_policy import validate_auth_dev_dependencies

    validate_auth_dev_dependencies(repo_root)

    gitleaks_config = repo_root / ".gitleaks.toml"
    gitleaks_cmd = ["gitleaks", "detect", "-v", "-s", str(repo_root)]
    if gitleaks_config.is_file():
        gitleaks_cmd.extend(["--config", str(gitleaks_config)])

    scanners: list[tuple[str, list[str], str | None]] = [
        ("gitleaks", gitleaks_cmd, None),
        (
            "govulncheck",
            [
                "govulncheck",
                "-C",
                str(repo_root / "services" / "proxy-gateway"),
                "./...",
            ],
            None,
        ),
        (
            "npm audit",
            ["npm", "audit", "--audit-level=moderate"],
            str(repo_root / "frontend"),
        ),
    ]

    missing = []
    for name, cmd, cwd in scanners:
        if shutil.which(cmd[0]) is None:
            missing.append(name)
            continue
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                run_env = os.environ.copy()
                if name == "govulncheck":
                    # CI setup-go may still install 1.25.12 until the workflow
                    # file can be updated (needs the GitHub `workflow` scope).
                    # Analyze against the go.mod patch that contains the
                    # stdlib fixes govulncheck reports for 1.25.12.
                    run_env["GOTOOLCHAIN"] = "go1.25.14"
                result = subprocess.run(
                    cmd,
                    cwd=cwd or str(repo_root),
                    capture_output=True,
                    text=True,
                    check=False,
                    env=run_env,
                )
                if result.returncode == 0:
                    last_error = None
                    break
                detail = redact((result.stderr or result.stdout or "").strip())
                if len(detail) > 2000:
                    detail = detail[-2000:]
                last_error = RuntimeError(
                    f"{name} scan failed (exit {result.returncode}): {detail}"
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt == max_retries:
                raise RuntimeError(
                    f"security scan {name!r} failed after {attempt + 1} attempts: {last_error}"
                )
        if last_error is not None:
            raise last_error

    # pip-audit against uv.lock via a temporary requirements export.
    pip_audit_cmd = [
        "uv",
        "run",
        "--project",
        str(repo_root / "tools" / "workflow"),
        "pip-audit",
    ]
    if shutil.which("uv") is None:
        missing.append("uv (required for pip-audit)")
    else:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as req_file:
            export_result = subprocess.run(
                [
                    "uv",
                    "export",
                    "--project",
                    str(repo_root / "services" / "api-service"),
                    "--no-hashes",
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if export_result.returncode != 0:
                raise RuntimeError(f"uv export failed for pip-audit: {export_result.stderr}")
            req_file.write(export_result.stdout)
            req_path = Path(req_file.name)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = subprocess.run(
                    pip_audit_cmd + ["-r", str(req_path), "--disable-pip", "--no-deps"],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    break
                last_error = RuntimeError(f"pip-audit scan failed (exit {result.returncode})")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt == max_retries:
                raise RuntimeError(f"security scan 'pip-audit' failed after {attempt + 1} attempts")
        req_path.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error

    if missing:
        raise RuntimeError(f"required security scanners are missing: {', '.join(missing)}")
