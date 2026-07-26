"""Deploy stack lifecycle (ADR 003 Layer D).

Public entry: ``make deploy`` / ``make deploy-down`` with ``mode=test|prod``.

Optional auth release gate (feature 004): set ``AUTH_RELEASE_MANIFEST`` or pass
Make ``auth_release_manifest=path.json`` so ``deploy_up`` calls
:func:`verify_auth_release_manifest` before Docker.
"""

from .lifecycle import (
    REQUIRED_AUTH_EVIDENCE_KEYS,
    deploy_down,
    deploy_up,
    verify_auth_activation,
    verify_auth_release_manifest,
)

__all__ = [
    "REQUIRED_AUTH_EVIDENCE_KEYS",
    "deploy_up",
    "deploy_down",
    "verify_auth_activation",
    "verify_auth_release_manifest",
]
