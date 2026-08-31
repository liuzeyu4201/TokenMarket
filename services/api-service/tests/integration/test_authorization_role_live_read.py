"""DB role changes take effect without trusting session role_snapshot."""

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


def test_role_change_after_login_uses_db_role(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    user = account_factory.create_active(role=UserRole.both, nickname="可变角色")
    issued = authz_sessions.issue(user, workspace="seller")
    force_session_cookie(authz_client, issued.cookie_value)

    assert (
        authz_client.post(
            "/api/v1/authorization/evaluate",
            json={"action": "seller_key.register"},
            headers=authz_headers(issued, with_csrf=False),
        ).status_code
        == 200
    )

    # Downgrade to buyer in DB; session cookie still has both snapshot
    authz_sessions.set_user_role(user.id, UserRole.buyer)
    denied = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "seller_key.register"},
        headers=authz_headers(issued, with_csrf=False),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN_ROLE"

    # Seller lens is invalid for buyer: fail-closed until workspace matches
    stale = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
        headers=authz_headers(issued, with_csrf=False),
    )
    assert stale.status_code == 403
    authz_sessions.set_workspace(issued.session_id, "buyer")
    ok = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "proxy_key.create"},
        headers=authz_headers(issued, with_csrf=False),
    )
    assert ok.status_code == 200
