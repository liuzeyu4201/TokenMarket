"""Auth release deploy gate using synthetic fixtures only (004 T091 / T099).

Must not read ``specs/004-phone-login-session-ui/evidence/``. All fixtures live
under ``tests/workflow/fixtures/auth-release/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from workflow.deploy_env.lifecycle import (
    REQUIRED_AUTH_EVIDENCE_KEYS,
    DeployError,
    auth_release_manifest_from_env,
    verify_auth_activation,
    verify_auth_release_manifest,
)

from .helpers import find_repo_root

ROOT = find_repo_root()
FIXTURES = ROOT / "tests" / "workflow" / "fixtures" / "auth-release"
REAL_EVIDENCE = ROOT / "specs" / "004-phone-login-session-ui" / "evidence"


def _fixture(name: str) -> Path:
    path = FIXTURES / name / "candidate.json"
    assert path.is_file(), f"missing fixture {path}"
    return path


def test_fixtures_directory_has_valid_and_invalid_cases() -> None:
    expected = {
        "valid",
        "missing-evidence",
        "hash-mismatch",
        "digest-mismatch",
        "synthetic-prod",
    }
    present = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
    assert expected <= present


def test_tests_do_not_read_real_evidence_tree() -> None:
    """Guard: this module and fixtures must stay decoupled from real evidence."""
    # Fixture tree is under tests/workflow — not under the real evidence path.
    assert "tests/workflow/fixtures/auth-release" in str(FIXTURES)
    assert FIXTURES.resolve() != REAL_EVIDENCE.resolve()
    assert REAL_EVIDENCE.resolve() not in FIXTURES.resolve().parents
    for path in FIXTURES.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".sha256"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            # Candidate JSON must not bind to the real evidence path.
            assert "specs/004-phone-login-session-ui/evidence" not in text
            # No secret-looking material in fixtures
            assert "tm_local_" not in text
            assert "sk-" not in text


def test_valid_manifest_passes() -> None:
    report = verify_auth_release_manifest(_fixture("valid"), target_mode="test")
    assert report["ok"] is True
    assert report["manifest_sha256"]
    assert set(report["evidence_keys"]) == set(REQUIRED_AUTH_EVIDENCE_KEYS)
    assert report["activation"]["ok"] is True
    assert report["activation"]["tls_ready"] is True


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    with pytest.raises(DeployError) as exc:
        verify_auth_release_manifest(missing)
    assert exc.value.code == "AUTH_MANIFEST_MISSING"


def test_missing_evidence_key_fails_closed() -> None:
    with pytest.raises(DeployError) as exc:
        verify_auth_release_manifest(_fixture("missing-evidence"), require_activation=False)
    assert exc.value.code == "AUTH_EVIDENCE_MISSING"
    assert "browser" in exc.value.message


def test_hash_mismatch_fails_closed() -> None:
    with pytest.raises(DeployError) as exc:
        verify_auth_release_manifest(_fixture("hash-mismatch"), require_activation=False)
    assert exc.value.code == "AUTH_HASH_MISMATCH"


def test_digest_mismatch_fails_closed() -> None:
    with pytest.raises(DeployError) as exc:
        verify_auth_release_manifest(_fixture("digest-mismatch"), require_activation=False)
    assert exc.value.code == "AUTH_DIGEST_MISMATCH"


def test_synthetic_prod_activation_fails_closed() -> None:
    with pytest.raises(DeployError) as exc:
        verify_auth_release_manifest(_fixture("synthetic-prod"), target_mode="prod")
    assert exc.value.code in {"AUTH_ACTIVATION_TLS", "AUTH_ACTIVATION_SMS"}


def test_activation_requires_dispatcher_cleanup_proxy_keys() -> None:
    with pytest.raises(DeployError) as exc:
        verify_auth_activation(
            {
                "tls_ready": True,
                "sms_adapter": "approved-provider",
                "browser_origins": [],
                "trusted_proxy_cidrs": ["10.0.0.0/8"],
                "hmac_keys_configured": True,
                "dispatcher_enabled": True,
                "cleanup_schedule_cron": "17 * * * *",
                "cleanup_batch_size": 500,
                "cleanup_max_runtime_seconds": 900,
            }
        )
    assert exc.value.code == "AUTH_ACTIVATION_INVALID"
    assert "browser_origins" in exc.value.message

    with pytest.raises(DeployError) as exc2:
        verify_auth_activation(
            {
                "tls_ready": True,
                "sms_adapter": "approved-provider",
                "browser_origins": ["https://app.example.test"],
                "trusted_proxy_cidrs": ["10.0.0.0/8"],
                "hmac_keys_configured": True,
                "dispatcher_enabled": False,
                "cleanup_schedule_cron": "17 * * * *",
                "cleanup_batch_size": 500,
                "cleanup_max_runtime_seconds": 900,
            }
        )
    assert "dispatcher" in exc2.value.message

    with pytest.raises(DeployError) as exc3:
        verify_auth_activation(
            {
                "tls_ready": True,
                "sms_adapter": "approved-provider",
                "browser_origins": ["https://app.example.test"],
                "trusted_proxy_cidrs": ["10.0.0.0/8"],
                "hmac_keys_configured": False,
                "dispatcher_enabled": True,
                "cleanup_schedule_cron": "17 * * * *",
                "cleanup_batch_size": 500,
                "cleanup_max_runtime_seconds": 900,
            }
        )
    assert "hmac_keys" in exc3.value.message


def test_auth_release_manifest_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_RELEASE_MANIFEST", raising=False)
    monkeypatch.delenv("auth_release_manifest", raising=False)
    assert auth_release_manifest_from_env() is None
    monkeypatch.setenv("AUTH_RELEASE_MANIFEST", "tests/workflow/fixtures/auth-release/valid/candidate.json")
    assert auth_release_manifest_from_env() is not None


def test_deploy_up_invokes_auth_gate_before_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When AUTH_RELEASE_MANIFEST is set, a bad manifest fails before docker."""
    from workflow.deploy_env import lifecycle as life

    monkeypatch.setenv(
        "AUTH_RELEASE_MANIFEST",
        str(_fixture("hash-mismatch")),
    )
    # If docker is contacted, fail the test.
    def _boom() -> None:
        raise AssertionError("docker must not be contacted when auth gate fails")

    monkeypatch.setattr(life, "_ensure_docker", _boom)
    code = life.deploy_up(
        ROOT,
        mode="test",
        mode_origin="command line",
        plain=True,
    )
    assert code == 1


def test_deploy_up_accepts_valid_auth_manifest_then_hits_later_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid auth manifest passes; deploy may still fail later (docker/config)."""
    from workflow.deploy_env import lifecycle as life

    monkeypatch.setenv("AUTH_RELEASE_MANIFEST", str(_fixture("valid")))
    # Short-circuit after auth gate by making docker missing.
    monkeypatch.setattr(
        life,
        "_ensure_docker",
        lambda: (_ for _ in ()).throw(life.DeployError("TOOL_MISSING", "docker skipped")),
    )
    code = life.deploy_up(
        ROOT,
        mode="test",
        mode_origin="command line",
        plain=True,
    )
    # Auth gate passed; TOOL_MISSING is still a clean fail-closed exit.
    assert code == 1


def test_compose_app_documents_auth_activation_hooks() -> None:
    text = (ROOT / "infra" / "docker" / "compose.app.yml").read_text(encoding="utf-8")
    for key in (
        "AUTH_BROWSER_ORIGINS",
        "AUTH_TRUSTED_PROXY_CIDRS",
        "AUTH_SMS_ADAPTER",
        "AUTH_DISPATCHER_LEASE_SECONDS",
        "AUTH_TLS_READY",
        "AUTH_CLEANUP_BATCH_SIZE",
    ):
        assert key in text, f"compose.app.yml missing auth hook {key}"


def test_required_evidence_keys_match_p1_blocking_set() -> None:
    assert "browser" in REQUIRED_AUTH_EVIDENCE_KEYS
    assert "backup_restore" in REQUIRED_AUTH_EVIDENCE_KEYS
    assert "traceability" in REQUIRED_AUTH_EVIDENCE_KEYS
    # Ensure valid fixture actually binds every required key
    payload = json.loads(_fixture("valid").read_text(encoding="utf-8"))
    assert REQUIRED_AUTH_EVIDENCE_KEYS <= set(payload["evidence"])
