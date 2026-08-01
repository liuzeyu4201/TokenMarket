"""HTTP evaluate matrix + session revoke (SC-006)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.users.models import UserRole
from tests.integration.conftest_authorization import (
    AuthzSessionFactory,
    authz_headers,
    force_session_cookie,
)

pytestmark = pytest.mark.integration


def test_buyer_seller_both_matrix_and_session_revoke(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    buyer = account_factory.create_active(role=UserRole.buyer, nickname="买")
    seller = account_factory.create_active(role=UserRole.seller, nickname="卖")
    both = account_factory.create_active(role=UserRole.both, nickname="双")

    # buyer: proxy create allowed (evaluate without mutation), seller register denied
    b_sess = authz_sessions.issue(buyer)
    force_session_cookie(authz_client, b_sess.cookie_value)
    ok = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
        headers=authz_headers(b_sess, with_csrf=False),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["code"] == "0"
    denied = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "seller_key.register"},
        headers=authz_headers(b_sess, with_csrf=False),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN_ROLE"

    # seller: opposite
    s_sess = authz_sessions.issue(seller)
    force_session_cookie(authz_client, s_sess.cookie_value)
    assert (
        authz_client.post(
            "/api/v1/authorization/evaluate",
            json={"action": "seller_key.register"},
            headers=authz_headers(s_sess, with_csrf=False),
        ).status_code
        == 200
    )
    assert (
        authz_client.post(
            "/api/v1/authorization/evaluate",
            json={"action": "proxy_key.create"},
            headers=authz_headers(s_sess, with_csrf=False),
        ).json()["code"]
        == "FORBIDDEN_ROLE"
    )

    # both: both allowed
    bo_sess = authz_sessions.issue(both)
    force_session_cookie(authz_client, bo_sess.cookie_value)
    for action in ("proxy_key.create", "seller_key.register"):
        res = authz_client.post(
            "/api/v1/authorization/evaluate",
            json={"action": action},
            headers=authz_headers(bo_sess, with_csrf=False),
        )
        assert res.status_code == 200, res.text

    # SC-006: revoke session → 401, never allow
    authz_sessions.revoke(bo_sess.session_id)
    force_session_cookie(authz_client, bo_sess.cookie_value)
    after = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
        headers=authz_headers(bo_sess, with_csrf=False),
    )
    assert after.status_code == 401
    assert after.json()["code"] == "UNAUTHENTICATED"


def test_missing_cookie_unauthenticated(authz_client: TestClient) -> None:
    res = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
    )
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"
