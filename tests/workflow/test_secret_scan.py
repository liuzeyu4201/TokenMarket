"""Secret scan and SF02 redaction contract tests (T059 / T081).

Generate synthetic suspected credentials and verify that a full-history scan
fails, locates the file, and does not echo the value in output. Also assert
lifecycle event/plain-text surfaces never leak SF02 secrets or workspace paths.

Open-source desensitization: the same module walks the real publishable tree
for operator home paths, PEM private-key armor, and non-placeholder env values.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from workflow.events import DiagnosticCodeV2, emit_event_v2
from workflow.local_env.lifecycle import LifecycleRunOutcome
from workflow.security import (
    format_desense_findings,
    load_gitleaks_allowlist_patterns,
    scan_text_for_desensitization,
    scan_tracked_tree_for_desensitization,
)

from .helpers import find_repo_root


@pytest.fixture
def gitleaks_available() -> bool:
    return shutil.which("gitleaks") is not None


# Assembled only at runtime so the contiguous credential is not in the tree.
_PROBE_SECRET = "sk-zz" + "abcdefghijklmnopqrstuvwxyz" + "9999"


def _run_gitleaks(scan_dir: Path, config: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "gitleaks",
            "dir",
            str(scan_dir),
            "-c",
            str(config),
            "--redact",
            "100",
            "-v",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(scan_dir),
    )


def test_gitleaks_detects_synthetic_credential(gitleaks_available: bool, tmp_path: Path) -> None:
    if not gitleaks_available:
        pytest.skip("gitleaks not installed on this host")

    repo_root = find_repo_root()
    (tmp_path / "leak.txt").write_text(f'api_key="{_PROBE_SECRET}"\n', encoding="utf-8")
    result = _run_gitleaks(tmp_path, repo_root / ".gitleaks.toml")
    assert result.returncode != 0, (
        "gitleaks should detect the synthetic credential: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _PROBE_SECRET not in result.stdout
    assert _PROBE_SECRET not in result.stderr


def test_repo_gitleaks_config_hits_formerly_excluded_path_classes(
    gitleaks_available: bool, tmp_path: Path
) -> None:
    if not gitleaks_available:
        pytest.skip("gitleaks not installed on this host")
    repo_root = find_repo_root()
    config = repo_root / ".gitleaks.toml"
    secret = _PROBE_SECRET
    classes = [
        tmp_path / "tests" / "workflow" / "leak.txt",
        tmp_path / "services" / "proxy-gateway" / "probe_test.go",
        tmp_path / "specs" / "leak.md",
        tmp_path / "项目开发" / "leak.md",
    ]
    for path in classes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'api_key="{secret}"\n', encoding="utf-8")
        result = _run_gitleaks(path.parent, config)
        assert result.returncode != 0, (
            f"repository gitleaks config must fail for {path}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


def test_fixtures_allowlisted_only_by_exact_inert_value(
    gitleaks_available: bool, tmp_path: Path
) -> None:
    if not gitleaks_available:
        pytest.skip("gitleaks not installed on this host")
    repo_root = find_repo_root()
    path = tmp_path / "fixture.txt"
    path.write_text('api_key="sk-synthetic-test-key-not-real"\n', encoding="utf-8")
    result = _run_gitleaks(tmp_path, repo_root / ".gitleaks.toml")
    assert result.returncode == 0, result.stdout + result.stderr


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
    blob = (
        json.dumps(list(outcome.events), ensure_ascii=False) + "\n" + "\n".join(outcome.plain_lines)
    )
    assert secret not in blob
    assert path not in blob
    assert "tm_local_" not in blob
    assert outcome.project_id.startswith("tmtest-")


def test_desense_scan_flags_operator_home_and_toolchain_path() -> None:
    user = "ci" + "-operator"
    text = f'PATH="/Users/{user}/.local/go1.25.12/bin:$PATH" make ci\n'
    findings = scan_text_for_desensitization("docs/evidence.md", text)
    assert any(item.kind == "operator-home-path" for item in findings)
    blob = format_desense_findings(findings)
    assert user not in blob
    assert "/Users/" not in blob


def test_desense_scan_allows_generic_sentinel_home_paths() -> None:
    text = "\n".join(
        [
            "workspace /Users/alice/Projects/TokenMarket is not inspectable",
            "trace at /Users/developer/Projects/TokenMarket/x.py",
            "under /Users/tmtest-security/workspace",
        ]
    )
    findings = scan_text_for_desensitization("tests/workflow/sentinels.py", text)
    assert findings == []


def test_desense_scan_flags_pem_private_key_armor() -> None:
    header = "-----BEGIN " + "RSA PRIVATE KEY-----"
    text = header + "\nAAAA\n-----END RSA PRIVATE KEY-----\n"
    findings = scan_text_for_desensitization("secrets/dev.pem", text)
    assert any(item.kind == "private-key-pem" for item in findings)
    assert "AAAA" not in format_desense_findings(findings)


def test_desense_scan_flags_non_allowlisted_credential_shaped_token() -> None:
    repo_root = find_repo_root()
    allowlist = load_gitleaks_allowlist_patterns(repo_root / ".gitleaks.toml")
    text = f'api_key="{_PROBE_SECRET}"\n'
    findings = scan_text_for_desensitization("tests/workflow/leak.txt", text, allowlist=allowlist)
    assert any(item.kind == "live-credential" for item in findings)
    assert _PROBE_SECRET not in format_desense_findings(findings)


def test_desense_scan_allows_exact_gitleaks_inert_values() -> None:
    repo_root = find_repo_root()
    allowlist = load_gitleaks_allowlist_patterns(repo_root / ".gitleaks.toml")
    text = 'api_key="sk-synthetic-test-key-not-real"\n'
    findings = scan_text_for_desensitization(
        "tests/workflow/fixture.txt", text, allowlist=allowlist
    )
    assert not any(item.kind == "live-credential" for item in findings)


def test_desense_scan_flags_live_tm_local_in_env_template() -> None:
    live = "tm_local_" + ("A" * 40)
    text = f"GRAFANA_ADMIN_PASSWORD={live}\n"
    findings = scan_text_for_desensitization(".env.example", text)
    assert any(item.kind == "env-live-secret" for item in findings)
    assert live not in format_desense_findings(findings)


def test_desense_scan_flags_usable_secret_without_placeholder_grammar() -> None:
    value = "usable-only-not-for-templates-xyz"
    text = f"AI_GATEWAY_KEY={value}\n"
    findings = scan_text_for_desensitization(".env.example", text)
    assert any(item.kind == "env-usable-secret" for item in findings)
    assert value not in format_desense_findings(findings)


def test_desense_scan_accepts_placeholder_env_template() -> None:
    text = (
        "MODE=local\n"
        "DATABASE_URL=postgresql://app:replace-me-with-a-generated-tm-local-secret"
        "@127.0.0.1:5432/tokenmarket\n"
        "AI_GATEWAY_KEY=sk-replace-me\n"
        "GRAFANA_ADMIN_PASSWORD=replace-me-with-a-generated-tm-local-secret\n"
    )
    findings = scan_text_for_desensitization(".env.example", text)
    assert findings == []


def test_gitleaks_config_has_no_path_wide_allowlist() -> None:
    config = (find_repo_root() / ".gitleaks.toml").read_text(encoding="utf-8")
    lowered = config.lower()
    assert "paths" not in lowered or "path-wide" in lowered
    assert "regexes" in lowered


def test_publishable_tree_is_desensitized() -> None:
    repo_root = find_repo_root()
    findings = scan_tracked_tree_for_desensitization(repo_root)
    assert findings == [], format_desense_findings(findings)


def test_gitleaks_detect_on_repository_history_is_clean(
    gitleaks_available: bool,
) -> None:
    if not gitleaks_available:
        pytest.skip("gitleaks not installed on this host")
    repo_root = find_repo_root()
    result = subprocess.run(
        [
            "gitleaks",
            "detect",
            "-v",
            "-s",
            str(repo_root),
            "--config",
            str(repo_root / ".gitleaks.toml"),
            "--redact",
            "100",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, output
    assert _PROBE_SECRET not in output


def test_committed_env_templates_are_unusable_placeholders() -> None:
    repo_root = find_repo_root()
    allowlist = load_gitleaks_allowlist_patterns(repo_root / ".gitleaks.toml")
    templates = [
        repo_root / ".env.example",
        repo_root / "frontend" / ".env.development.example",
    ]
    for path in templates:
        assert path.is_file(), path
        rel = str(path.relative_to(repo_root))
        text = path.read_text(encoding="utf-8")
        findings = scan_text_for_desensitization(rel, text, allowlist=allowlist)
        assert findings == [], format_desense_findings(findings)
