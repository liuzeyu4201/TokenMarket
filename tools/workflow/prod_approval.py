"""Independent production approval proofs bound to action, target, and digests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, MutableSet

from .mode import ModeError

_SEEN_NONCES: set[str] = set()


def _canonical(payload: Mapping[str, Any]) -> bytes:
    body = {
        "action": payload["action"],
        "environment": payload["environment"],
        "target": payload["target"],
        "commit_sha": payload["commit_sha"],
        "image_digests": list(payload.get("image_digests") or ()),
        "nonce": payload["nonce"],
        "expires_at": payload["expires_at"],
        "issuer": payload["issuer"],
        "subject": payload["subject"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def approval_hmac_key(raw: str | None = None) -> bytes:
    text = (raw if raw is not None else os.environ.get("PROD_APPROVAL_HMAC_KEY", "")).strip()
    if len(text) < 32:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "PROD_APPROVAL_HMAC_KEY must be at least 32 characters",
        )
    return text.encode("utf-8")


def sign_approval(payload: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def issue_approval(
    *,
    issuer: str,
    subject: str,
    action: str,
    environment: str,
    target: str,
    commit_sha: str,
    image_digests: Iterable[str],
    nonce: str,
    expires_at: str,
    key: bytes,
) -> dict[str, Any]:
    if issuer.strip() == "" or subject.strip() == "":
        raise ModeError("PROD_APPROVAL_REQUIRED", "issuer and subject are required")
    if issuer == subject:
        raise ModeError(
            "SELF_APPROVAL_FORBIDDEN",
            "an operator cannot approve their own production action",
        )
    payload: dict[str, Any] = {
        "action": action,
        "environment": environment,
        "target": target,
        "commit_sha": commit_sha,
        "image_digests": list(image_digests),
        "nonce": nonce,
        "expires_at": expires_at,
        "issuer": issuer,
        "subject": subject,
    }
    payload["signature"] = sign_approval(payload, key)
    return payload


def _parse_expires(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def verify_approval(
    proof: Mapping[str, Any],
    *,
    operator: str,
    action: str,
    environment: str,
    target: str,
    image_digests: Iterable[str],
    key: bytes,
    now: datetime | None = None,
    seen_nonces: MutableSet[str] | None = None,
) -> None:
    required = {
        "action",
        "environment",
        "target",
        "commit_sha",
        "image_digests",
        "nonce",
        "expires_at",
        "issuer",
        "subject",
        "signature",
    }
    missing = required - proof.keys()
    if missing:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            f"production approval proof missing fields: {sorted(missing)}",
        )
    issuer = str(proof["issuer"])
    subject = str(proof["subject"])
    if issuer == subject or subject != operator:
        raise ModeError(
            "SELF_APPROVAL_FORBIDDEN",
            "an operator cannot approve their own production action",
        )
    expected_sig = sign_approval(proof, key)
    presented = str(proof["signature"])
    if not hmac.compare_digest(expected_sig, presented):
        raise ModeError("PROD_APPROVAL_INVALID", "forged or corrupted approval proof")
    if str(proof["action"]) != action or str(proof["environment"]) != environment:
        raise ModeError("PROD_APPROVAL_INVALID", "approval is bound to a different action")
    if str(proof["target"]) != target:
        raise ModeError("PROD_APPROVAL_INVALID", "approval is bound to a different target")
    presented_digests = [str(x) for x in (proof.get("image_digests") or ())]
    expected_digests = [str(x) for x in image_digests]
    if presented_digests != expected_digests:
        raise ModeError("PROD_APPROVAL_INVALID", "approval digest binding mismatch")
    when = now if now is not None else datetime.now(timezone.utc)
    try:
        expires = _parse_expires(str(proof["expires_at"]))
    except ValueError as exc:
        raise ModeError("PROD_APPROVAL_INVALID", "approval expiry is malformed") from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= when:
        raise ModeError("PROD_APPROVAL_INVALID", "approval proof has expired")
    nonce = str(proof["nonce"])
    registry = _SEEN_NONCES if seen_nonces is None else seen_nonces
    if nonce in registry:
        raise ModeError("PROD_APPROVAL_INVALID", "approval proof was replayed")
    registry.add(nonce)


def unix_expires_in(seconds: int) -> str:
    return datetime.fromtimestamp(time.time() + seconds, tz=timezone.utc).isoformat()
