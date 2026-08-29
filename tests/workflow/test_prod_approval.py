"""Independent production approval proofs (no self-approval)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from workflow.mode import ModeError, require_production_approval, validate_mode
from workflow.prod_approval import issue_approval, unix_expires_in, verify_approval

KEY = b"k" * 32
DIGEST = "sha256:" + ("a" * 64)


def _proof(**overrides: object) -> dict:
    payload = issue_approval(
        issuer="alice",
        subject="bob",
        action="deploy",
        environment="prod",
        target="tokenmarket-prod",
        commit_sha="abc123",
        image_digests=(DIGEST,),
        nonce="nonce-1",
        expires_at=unix_expires_in(600),
        key=KEY,
    )
    payload.update(overrides)
    if "signature" not in overrides:
        from workflow.prod_approval import sign_approval

        payload["signature"] = sign_approval(payload, KEY)
    return payload


def test_operator_cannot_approve_own_production_action() -> None:
    with pytest.raises(ModeError) as exc:
        issue_approval(
            issuer="bob",
            subject="bob",
            action="deploy",
            environment="prod",
            target="t",
            commit_sha="x",
            image_digests=(),
            nonce="n",
            expires_at=unix_expires_in(60),
            key=KEY,
        )
    assert exc.value.code == "SELF_APPROVAL_FORBIDDEN"


def test_forged_expired_replayed_wrong_target_wrong_digest_fail() -> None:
    seen: set[str] = set()
    good = _proof()
    verify_approval(
        good,
        operator="bob",
        action="deploy",
        environment="prod",
        target="tokenmarket-prod",
        image_digests=(DIGEST,),
        key=KEY,
        seen_nonces=seen,
    )
    forged = dict(good)
    forged["signature"] = "00" * 32
    with pytest.raises(ModeError):
        verify_approval(
            forged,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=set(),
        )
    expired = _proof(
        expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        nonce="nonce-expired",
    )
    with pytest.raises(ModeError):
        verify_approval(
            expired,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=set(),
        )
    with pytest.raises(ModeError):
        verify_approval(
            good,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=seen,
        )
    with pytest.raises(ModeError):
        verify_approval(
            _proof(nonce="n2"),
            operator="bob",
            action="deploy",
            environment="prod",
            target="other-target",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=set(),
        )
    other = "sha256:" + ("b" * 64)
    with pytest.raises(ModeError):
        verify_approval(
            _proof(nonce="n3"),
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(other,),
            key=KEY,
            seen_nonces=set(),
        )


def test_require_production_approval_rejects_missing_proof() -> None:
    selection = validate_mode("prod", "command")
    with pytest.raises(ModeError):
        require_production_approval(selection)


def test_self_issued_proof_with_caller_selected_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tm-approval-trust-root: operator-held issue key cannot mint production proofs."""
    monkeypatch.setenv("PROD_APPROVAL_ISSUE_KEY", "i" * 32)
    monkeypatch.setenv("PROD_APPROVAL_VERIFY_KEY", KEY.decode("utf-8"))
    monkeypatch.setenv("PROD_APPROVAL_ISSUER_ALLOWLIST", "alice")
    proof = _proof()
    selection = validate_mode("prod", "command")
    with pytest.raises(ModeError) as exc:
        require_production_approval(
            selection,
            approval_proof=proof,
            hmac_key=KEY,
            operator="bob",
            action="deploy",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
        )
    assert exc.value.code == "SELF_ISSUED_APPROVAL"


def test_hmac_verify_key_without_issue_key_cannot_authorize(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """HMAC VERIFY_KEY is mint capability even when ISSUE_KEY is absent."""
    monkeypatch.delenv("PROD_APPROVAL_ISSUE_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_HMAC_KEY", raising=False)
    monkeypatch.setenv("PROD_APPROVAL_VERIFY_KEY", KEY.decode("utf-8"))
    monkeypatch.setenv("PROD_APPROVAL_ISSUER_ALLOWLIST", "alice")
    monkeypatch.setenv("PROD_APPROVAL_NONCE_DIR", str(tmp_path / "nonces"))
    proof = _proof()
    selection = validate_mode("prod", "command")
    with pytest.raises(ModeError) as exc:
        require_production_approval(
            selection,
            approval_proof=proof,
            operator="bob",
            action="deploy",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
        )
    assert exc.value.code == "SELF_ISSUED_APPROVAL"


def test_caller_selected_key_without_host_verify_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROD_APPROVAL_ISSUE_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_VERIFY_KEY", raising=False)
    proof = _proof()
    selection = validate_mode("prod", "command")
    with pytest.raises(ModeError) as exc:
        require_production_approval(
            selection,
            approval_proof=proof,
            hmac_key=KEY,
            operator="bob",
        )
    assert exc.value.code in {"SELF_ISSUED_APPROVAL", "PROD_APPROVAL_REQUIRED"}


def test_proof_for_commit_a_cannot_authorize_commit_b() -> None:
    """tm-approval-commit-binding."""
    proof = _proof()
    with pytest.raises(ModeError) as exc:
        verify_approval(
            proof,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=set(),
            expected_commit_sha="ffffffffffffffff",
        )
    assert "commit" in exc.value.message


def test_dirty_worktree_fails_before_mutation() -> None:
    proof = _proof()
    with pytest.raises(ModeError) as exc:
        verify_approval(
            proof,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=set(),
            expected_commit_sha="abc123",
            dirty_worktree=True,
        )
    assert "dirty" in exc.value.message


def test_durable_nonce_consumed_across_processes(tmp_path) -> None:
    """tm-approval-replay: two processes sharing one durable store."""
    from workflow.prod_approval import consume_nonce_durable, verify_approval

    store = tmp_path / "nonces"
    proof = _proof(nonce="durable-nonce-1")
    verify_approval(
        proof,
        operator="bob",
        action="deploy",
        environment="prod",
        target="tokenmarket-prod",
        image_digests=(DIGEST,),
        key=KEY,
        seen_nonces=None,
        durable_nonce_dir=store,
    )
    with pytest.raises(ModeError) as exc:
        verify_approval(
            proof,
            operator="bob",
            action="deploy",
            environment="prod",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
            key=KEY,
            seen_nonces=None,
            durable_nonce_dir=store,
        )
    assert "replay" in exc.value.message
    with pytest.raises(ModeError):
        consume_nonce_durable("durable-nonce-1", store)


def test_missing_nonce_dir_fails_closed_on_production_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflow.prod_approval import generate_approval_keypair, issue_asymmetric_approval

    priv, pub = generate_approval_keypair()
    monkeypatch.delenv("PROD_APPROVAL_ISSUE_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_VERIFY_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_HMAC_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_NONCE_DIR", raising=False)
    monkeypatch.setenv("PROD_APPROVAL_VERIFY_PUBKEY", pub.decode("utf-8"))
    monkeypatch.setenv("PROD_APPROVAL_ISSUER_ALLOWLIST", "alice")
    proof = issue_asymmetric_approval(
        issuer="alice",
        subject="bob",
        action="deploy",
        environment="prod",
        target="tokenmarket-prod",
        commit_sha="abc123",
        image_digests=(DIGEST,),
        nonce="nonce-dir-missing",
        expires_at=unix_expires_in(600),
        private_pem=priv,
    )
    with pytest.raises(ModeError) as exc:
        require_production_approval(
            validate_mode("prod", "command"),
            approval_proof=proof,
            operator="bob",
            action="deploy",
            target="tokenmarket-prod",
            image_digests=(DIGEST,),
        )
    assert exc.value.code == "PROD_APPROVAL_REQUIRED"
    assert "NONCE" in exc.value.message.upper()


def test_two_processes_require_production_approval_env_nonce_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """tm-approval-replay: two processes, env nonce dir, no injected durable_nonce_dir."""
    import json
    import os
    import subprocess
    import sys

    from workflow.prod_approval import generate_approval_keypair, issue_asymmetric_approval

    priv, pub = generate_approval_keypair()
    nonce_dir = tmp_path / "nonces"
    monkeypatch.delenv("PROD_APPROVAL_ISSUE_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_VERIFY_KEY", raising=False)
    monkeypatch.delenv("PROD_APPROVAL_HMAC_KEY", raising=False)
    monkeypatch.setenv("PROD_APPROVAL_VERIFY_PUBKEY", pub.decode("utf-8"))
    monkeypatch.setenv("PROD_APPROVAL_ISSUER_ALLOWLIST", "alice")
    monkeypatch.setenv("PROD_APPROVAL_NONCE_DIR", str(nonce_dir))
    proof = issue_asymmetric_approval(
        issuer="alice",
        subject="bob",
        action="deploy",
        environment="prod",
        target="tokenmarket-prod",
        commit_sha="abc123",
        image_digests=(DIGEST,),
        nonce="shared-across-processes",
        expires_at=unix_expires_in(600),
        private_pem=priv,
    )
    child_env = os.environ.copy()
    child_env["TOKENMARKET_PROD_APPROVAL"] = json.dumps(proof)
    script = (
        "import json, os, sys\n"
        "from workflow.mode import require_production_approval, validate_mode\n"
        "proof = json.loads(os.environ['TOKENMARKET_PROD_APPROVAL'])\n"
        "require_production_approval(\n"
        "    validate_mode('prod', 'command'),\n"
        "    approval_proof=proof,\n"
        "    operator='bob',\n"
        "    action='deploy',\n"
        "    target='tokenmarket-prod',\n"
        "    image_digests=tuple(proof['image_digests']),\n"
        ")\n"
        "print('AUTHORIZED')\n"
    )
    first = subprocess.run(
        [sys.executable, "-c", script],
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert "AUTHORIZED" in first.stdout
    second = subprocess.run(
        [sys.executable, "-c", script],
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode != 0
    combined = second.stdout + second.stderr
    assert "AUTHORIZED" not in combined
    assert "replay" in combined.lower() or "PROD_APPROVAL_INVALID" in combined


def test_prod_deploy_dirty_worktree_fails_before_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from workflow.deploy_env import lifecycle as life

    monkeypatch.setattr(
        "workflow.release_candidate.git_tree_clean", lambda _root: False
    )
    monkeypatch.setattr(
        "workflow.release_candidate.git_commit_sha", lambda _root: "abc123"
    )

    def _boom() -> None:
        raise AssertionError("docker must not be contacted for a dirty worktree")

    monkeypatch.setattr(life, "_ensure_docker", _boom)
    monkeypatch.setenv("TOKENMARKET_DEPLOY_RUN_ID", "run-1")
    code = life.deploy_up(tmp_path, mode="prod", mode_origin="command", plain=True)
    assert code != 0
