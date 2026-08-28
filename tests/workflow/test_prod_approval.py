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
