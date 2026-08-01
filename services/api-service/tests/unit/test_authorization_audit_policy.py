"""Which decisions require per-request audit."""

from __future__ import annotations

from app.domain.authorization.audit import requires_per_request_audit
from app.domain.authorization.matrix import Action


def test_deny_requires_audit() -> None:
    assert requires_per_request_audit(
        allowed=False, action=Action.proxy_key_use, is_state_change=False
    )


def test_use_allow_no_audit() -> None:
    assert not requires_per_request_audit(
        allowed=True, action=Action.proxy_key_use, is_state_change=False
    )


def test_route_allow_no_audit() -> None:
    assert not requires_per_request_audit(
        allowed=True,
        action=Action.route_candidate_exclude_self,
        is_state_change=False,
    )


def test_state_change_requires_audit() -> None:
    assert requires_per_request_audit(
        allowed=True, action=Action.seller_key_register, is_state_change=True
    )
