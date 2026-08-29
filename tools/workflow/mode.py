"""Environment mode selection and production approval.

Implements the contract from
``shared/contracts/repository-workflow/v1/environment-mode.md``.
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from typing import Any

VALID_MODES = {"local", "test", "prod"}


class ModeError(Exception):
    """Raised when mode selection or approval is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ModeSelection:
    mode: str
    origin: str
    approved: bool = False
    approval_reference: str = ""


def validate_mode(mode: str | None, origin: str) -> ModeSelection:
    """Validate a mode value and its Make variable origin.

    Only explicit command-line ``mode=local|test|prod`` is accepted. Shell or
    file origins cannot escalate to ``test`` or ``prod``.
    """
    if mode is None or mode == "":
        return ModeSelection(mode="local", origin="omitted")

    if mode not in VALID_MODES:
        raise ModeError("INVALID_MODE", f"invalid mode {mode!r}; must be one of {VALID_MODES}")

    # Only direct command-line origin may select non-local environments.
    # ``command`` is the shorthand used by tests and thin callers; ``command line``
    # is the Make ``origin`` value for command-line variables.
    if origin not in ("command", "command line", "override") and mode in (
        "test",
        "prod",
    ):
        raise ModeError(
            "INVALID_MODE",
            f"mode={mode} from origin {origin!r} is not allowed; pass it on the make command line",
        )

    return ModeSelection(mode=mode, origin=origin)


def require_production_approval(
    selection: ModeSelection,
    *,
    interactive: bool = True,
    approval_proof: dict[str, Any] | None = None,
    confirmation_phrase: str = "deploy-to-production",
    hmac_key: bytes | None = None,
    operator: str | None = None,
    action: str | None = None,
    target: str | None = None,
    image_digests: tuple[str, ...] | None = None,
    expected_commit_sha: str | None = None,
    expected_run_id: str | None = None,
    expected_manifest_digest: str | None = None,
    dirty_worktree: bool = False,
    durable_nonce_dir: Any = None,
) -> ModeSelection:
    """Require a signed approval issued by a separately authenticated principal."""
    if selection.mode != "prod":
        return selection

    from pathlib import Path

    from .prod_approval import (
        production_verify_key,
        refuse_hmac_mint_authority,
        verify_approval,
    )

    if not approval_proof:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "production mode requires a signed independent approval proof",
        )

    who = str(operator or os.environ.get("TOKENMARKET_OPERATOR") or getpass.getuser() or "")
    if not who:
        raise ModeError("PROD_APPROVAL_REQUIRED", "production operator identity is required")
    bound_action = str(action or approval_proof.get("action") or "deploy")
    bound_target = str(target if target is not None else approval_proof.get("target") or "")
    bound_digests = image_digests
    if bound_digests is None:
        bound_digests = tuple(str(x) for x in (approval_proof.get("image_digests") or ()))
    refuse_hmac_mint_authority(hmac_key=hmac_key)
    production_verify_key(hmac_key=hmac_key)
    nonce_dir = Path(durable_nonce_dir) if durable_nonce_dir is not None else None
    verify_approval(
        approval_proof,
        operator=who,
        action=bound_action,
        environment="prod",
        target=bound_target,
        image_digests=bound_digests,
        key=b"",
        expected_commit_sha=expected_commit_sha,
        expected_run_id=expected_run_id,
        expected_manifest_digest=expected_manifest_digest,
        dirty_worktree=dirty_worktree,
        durable_nonce_dir=nonce_dir,
        enforce_issuer_allowlist=True,
        require_asymmetric=True,
    )
    return ModeSelection(
        mode="prod",
        origin=selection.origin,
        approved=True,
        approval_reference=str(approval_proof.get("nonce") or approval_proof.get("signature")),
    )
