"""Security helpers: redaction, placeholder validation, and desensitization scan.

This module provides the minimum redaction and placeholder validation used by
``events.py`` and ``cli.py`` in SF01, plus the tracked-tree desensitization
scan used before publishing the repository.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
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


def parse_env_assignments(text: str) -> dict[str, str]:
    """Parse ``.env``-style assignments, ignoring comments and blank lines."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            result[name.strip()] = value.strip()
    return result


def load_env_example(path: Any) -> dict[str, str]:
    """Parse a .env.example-style file into name/value entries."""
    return parse_env_assignments(Path(path).read_text(encoding="utf-8"))


# Generic home directory names used as sentinels/placeholders in tests and docs.
# Real operator or workstation names must not be added here.
_GENERIC_HOME_USERS = frozenset(
    {
        "alice",
        "bob",
        "developer",
        "user",
        "runner",
        "example",
        "workstation",
        "contributor",
        "operator",
    }
)

_UNIX_HOME_RE = re.compile(r"(?:/Users|/home)/([A-Za-z0-9._-]+)/")
_WINDOWS_HOME_RE = re.compile(
    r"[A-Za-z]:\\Users\\([A-Za-z0-9._-]+)\\",
    re.IGNORECASE,
)
_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
)
_TM_LOCAL_LIVE_RE = re.compile(r"tm_local_[A-Za-z0-9_-]{32,}")
_SECRET_ENV_NAME_RE = re.compile(
    r"(?:^|_)(?:PASSWORD|SECRET|PEPPER|API_KEY|HMAC_KEY|GATEWAY_KEY|" r"KEY_MATERIAL|TOKEN)(?:_|$)",
    re.IGNORECASE,
)
_URL_SECRET_ENV_NAMES = frozenset({"DATABASE_URL", "REDIS_URL", "ADMIN_DATABASE_URL"})
_GITLEAKS_ALLOWLIST_ITEM_RE = re.compile(r"'''([^']+)'''")
_BINARY_SUFFIXES = frozenset(
    {
        ".xlsx",
        ".docx",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".zip",
        ".woff",
        ".woff2",
        ".ico",
        ".bin",
    }
)


@dataclass(frozen=True)
class DesenseFinding:
    """A desensitization hit. Messages carry path/kind/line only — never the value."""

    path: str
    kind: str
    line: int

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.kind}"


def is_generic_home_user(name: str) -> bool:
    """Return True if *name* is a documented placeholder, not an operator identity."""
    lowered = name.lower()
    if lowered.startswith("tmtest-"):
        return True
    return lowered in _GENERIC_HOME_USERS


def load_gitleaks_allowlist_patterns(config_path: Path) -> tuple[re.Pattern[str], ...]:
    """Load exact-value allowlist regexes from the repository gitleaks config."""
    text = Path(config_path).read_text(encoding="utf-8")
    patterns: list[re.Pattern[str]] = []
    for raw in _GITLEAKS_ALLOWLIST_ITEM_RE.findall(text):
        patterns.append(re.compile(raw))
    return tuple(patterns)


def _is_env_template(relative_path: str) -> bool:
    name = Path(relative_path).name
    return name == ".env.example" or name.endswith(".example")


def _is_secret_env_name(name: str) -> bool:
    if name in _URL_SECRET_ENV_NAMES:
        return True
    return bool(_SECRET_ENV_NAME_RE.search(name))


def _is_binary_path(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:8192]
    except OSError:
        return True
    return b"\0" in chunk


def _allowlisted_or_placeholder(value: str, allowlist: tuple[re.Pattern[str], ...]) -> bool:
    if is_safe_placeholder(value):
        return True
    return any(pattern.search(value) for pattern in allowlist)


def _scan_env_template_values(relative_path: str, text: str) -> list[DesenseFinding]:
    findings: list[DesenseFinding] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip("\"'")
        if not value:
            continue
        if _TM_LOCAL_LIVE_RE.search(value):
            findings.append(DesenseFinding(relative_path, "env-live-secret", line_no))
            continue
        if _is_secret_env_name(name) and not is_safe_placeholder(value):
            findings.append(DesenseFinding(relative_path, "env-usable-secret", line_no))
    return findings


def scan_text_for_desensitization(
    relative_path: str,
    text: str,
    *,
    allowlist: tuple[re.Pattern[str], ...] = (),
) -> list[DesenseFinding]:
    """Scan one file's text for leaks that default gitleaks rules miss or must confirm."""
    findings: list[DesenseFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _PEM_PRIVATE_KEY_RE.search(line):
            findings.append(DesenseFinding(relative_path, "private-key-pem", line_no))
        for match in _UNIX_HOME_RE.finditer(line):
            if not is_generic_home_user(match.group(1)):
                findings.append(DesenseFinding(relative_path, "operator-home-path", line_no))
        for match in _WINDOWS_HOME_RE.finditer(line):
            if not is_generic_home_user(match.group(1)):
                findings.append(DesenseFinding(relative_path, "operator-home-path", line_no))
        for match in _SECRET_PATTERNS[0].finditer(line):
            if _allowlisted_or_placeholder(match.group(0), allowlist):
                continue
            findings.append(DesenseFinding(relative_path, "live-credential", line_no))
    if _is_env_template(relative_path):
        findings.extend(_scan_env_template_values(relative_path, text))
    return findings


def _listed_publishable_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],
        cwd=str(repo_root),
        capture_output=True,
        check=True,
    )
    names = [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]
    return names


def scan_tracked_tree_for_desensitization(repo_root: Path) -> list[DesenseFinding]:
    """Walk publishable files (tracked + untracked non-ignored) and return leak findings."""
    root = Path(repo_root)
    config = root / ".gitleaks.toml"
    allowlist = load_gitleaks_allowlist_patterns(config) if config.is_file() else ()
    findings: list[DesenseFinding] = []
    for rel in _listed_publishable_files(root):
        path = root / rel
        if not path.is_file() or _is_binary_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text_for_desensitization(rel, text, allowlist=allowlist))
    return findings


def format_desense_findings(findings: list[DesenseFinding]) -> str:
    """Format findings as path:line:kind lines with no secret values."""
    return "\n".join(item.format() for item in findings)


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


PYTHON_LOCK_PROJECTS: tuple[str, ...] = (
    "services/api-service",
    "services/billing-service",
    "services/admin-service",
    "tools/workflow",
)


def iter_python_lock_projects(repo_root: Path) -> list[Path]:
    """Return every committed Python lock environment; fail if any is missing."""
    root = Path(repo_root)
    found: list[Path] = []
    missing: list[str] = []
    for rel in PYTHON_LOCK_PROJECTS:
        lock = root / rel / "uv.lock"
        if not lock.is_file():
            missing.append(rel)
        else:
            found.append(root / rel)
    if missing:
        raise RuntimeError(
            "python lock missing for pip-audit: " + ", ".join(missing)
        )
    if len(found) != len(PYTHON_LOCK_PROJECTS):
        raise RuntimeError("python lock audit coverage is incomplete")
    return found


def python_lock_audit_plan(repo_root: Path) -> list[dict[str, Any]]:
    """Describe the independent export+audit commands for each Python lock."""
    root = Path(repo_root)
    workflow_project = str(root / "tools" / "workflow")
    plan: list[dict[str, Any]] = []
    for project in iter_python_lock_projects(root):
        plan.append(
            {
                "project": str(project.relative_to(root)).replace("\\", "/"),
                "export_cmd": [
                    "uv",
                    "export",
                    "--frozen",
                    "--project",
                    str(project),
                    "--no-hashes",
                ],
                "audit_cmd_prefix": [
                    "uv",
                    "run",
                    "--project",
                    workflow_project,
                    "pip-audit",
                ],
            }
        )
    return plan


def audit_python_locks(repo_root: Path, *, max_retries: int = 1) -> None:
    """Export and pip-audit every committed Python lock independently."""
    import subprocess
    import tempfile

    root = Path(repo_root)
    for item in python_lock_audit_plan(root):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as req_file:
            export_result = subprocess.run(
                item["export_cmd"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            if export_result.returncode != 0:
                raise RuntimeError(
                    f"uv export failed for pip-audit ({item['project']}): "
                    f"{export_result.stderr}"
                )
            req_file.write(export_result.stdout)
            req_path = Path(req_file.name)
        last_error: Exception | None = None
        audit_cmd = item["audit_cmd_prefix"] + [
            "-r",
            str(req_path),
            "--disable-pip",
            "--no-deps",
        ]
        for attempt in range(max_retries + 1):
            try:
                result = subprocess.run(
                    audit_cmd,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    last_error = None
                    break
                last_error = RuntimeError(
                    f"pip-audit scan failed for {item['project']} "
                    f"(exit {result.returncode})"
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt == max_retries:
                req_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"security scan 'pip-audit' failed for {item['project']} "
                    f"after {attempt + 1} attempts"
                )
        req_path.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error


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

    if shutil.which("uv") is None:
        missing.append("uv (required for pip-audit)")
    else:
        audit_python_locks(repo_root, max_retries=max_retries)

    if missing:
        raise RuntimeError(f"required security scanners are missing: {', '.join(missing)}")
