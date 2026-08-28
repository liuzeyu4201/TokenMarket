"""Production image references must be digest-pinned."""

from __future__ import annotations

import pytest

from workflow.deploy_env.lifecycle import DeployError
from workflow.image_pin import require_digest_pinned_image, verify_approved_digests

GOOD = "tokenmarket/api-service:0.1.0@sha256:" + ("a" * 64)


def test_tag_only_production_image_refs_are_rejected() -> None:
    for ref in (
        "tokenmarket/proxy-gateway:0.1.0",
        "tokenmarket/api-service:latest",
        "alpine:3.20",
        "tokenmarket/frontend",
    ):
        with pytest.raises(DeployError) as exc:
            require_digest_pinned_image(ref, name="IMAGE")
        assert exc.value.code == "INVALID_CONFIG"
    assert require_digest_pinned_image(GOOD) == GOOD


def test_rewritten_tag_after_approval_fails_digest_verification() -> None:
    approved = (GOOD,)
    def inspect(_name: str) -> str:
        return "sha256:" + ("b" * 64)

    with pytest.raises(DeployError) as exc:
        verify_approved_digests(approved, inspect=inspect)
    assert exc.value.code == "DIGEST_MISMATCH"

    def inspect_ok(_name: str) -> str:
        return "sha256:" + ("a" * 64)

    verify_approved_digests(approved, inspect=inspect_ok)
