"""reason_code → public business code / HTTP mapping."""

from __future__ import annotations

from app.domain.authorization.codes import (
    AuthzCode,
    ReasonCode,
    http_status_for_code,
    public_outcome,
)


def test_role_denied_is_403() -> None:
    o = public_outcome(ReasonCode.ROLE_DENIED)
    assert o.code is AuthzCode.FORBIDDEN_ROLE
    assert o.http_status == 403


def test_not_owner_and_missing_same_public() -> None:
    a = public_outcome(ReasonCode.NOT_OWNER)
    b = public_outcome(ReasonCode.RESOURCE_MISSING)
    c = public_outcome(ReasonCode.RESOURCE_SOFT_DELETED)
    assert a.code is b.code is c.code is AuthzCode.RESOURCE_NOT_FOUND
    assert a.http_status == b.http_status == c.http_status == 404


def test_account_states_unavailable() -> None:
    for r in (
        ReasonCode.ACCOUNT_SUSPENDED,
        ReasonCode.ACCOUNT_DELETED,
        ReasonCode.ACCOUNT_INACTIVE,
    ):
        o = public_outcome(r)
        assert o.code is AuthzCode.ACCOUNT_UNAVAILABLE
        assert o.http_status == 403


def test_self_route_empty_404() -> None:
    o = public_outcome(ReasonCode.SELF_ROUTE_EMPTY)
    assert o.code is AuthzCode.NO_ROUTE_CANDIDATE
    assert o.http_status == 404


def test_audit_and_fact_store_503() -> None:
    assert public_outcome(ReasonCode.AUDIT_PERSIST_FAILED).http_status == 503
    assert public_outcome(ReasonCode.FACT_STORE_UNAVAILABLE).http_status == 503
    assert http_status_for_code(AuthzCode.SERVICE_UNAVAILABLE) == 503
