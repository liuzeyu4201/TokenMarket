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
) -> ModeSelection:
    """Require a separate approval gate for production mode."""
    if selection.mode != "prod":
        return selection

    if approval_proof:
        required = {"action", "commit_sha", "run_id", "approval_reference"}
        missing = required - approval_proof.keys()
        if missing:
            raise ModeError(
                "PROD_APPROVAL_REQUIRED",
                f"production approval proof missing fields: {sorted(missing)}",
            )
        return ModeSelection(
            mode="prod",
            origin=selection.origin,
            approved=True,
            approval_reference=str(approval_proof["approval_reference"]),
        )

    if interactive and os.isatty(0):
        prompt = (
            "Production mode selected. Type the confirmation phrase "
            f"'{confirmation_phrase}' to proceed: "
        )
        answer = getpass.getpass(prompt)
        if answer.strip() != confirmation_phrase:
            raise ModeError(
                "PROD_APPROVAL_REQUIRED",
                "production confirmation phrase mismatch",
            )
        return ModeSelection(
            mode="prod",
            origin=selection.origin,
            approved=True,
            approval_reference="interactive-phrase",
        )

    raise ModeError(
        "PROD_APPROVAL_REQUIRED",
        "production mode requires explicit approval; none provided",
    )
