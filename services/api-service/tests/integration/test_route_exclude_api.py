"""HTTP self-route exclusion endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.domain.users.models import UserRole
from tests.integration.conftest_authorization import (
    AuthzSessionFactory,
    authz_headers,
    force_session_cookie,
)

pytestmark = pytest.mark.integration


def test_exclude_self_http(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    user = account_factory.create_active(role=UserRole.both, nickname="路由")
    other_user = account_factory.create_active(role=UserRole.seller, nickname="他人")
    issued = authz_sessions.issue(user)
    force_session_cookie(authz_client, issued.cookie_value)
    self_created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "seller_key", "action": "seller_key.register"},
        headers=authz_headers(issued),
    )
    assert self_created.status_code == 200, self_created.text
    self_id = self_created.json()["data"]["resource_id"]

    other_issued = authz_sessions.issue(other_user)
    force_session_cookie(authz_client, other_issued.cookie_value)
    other_created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "seller_key", "action": "seller_key.register"},
        headers=authz_headers(other_issued),
    )
    assert other_created.status_code == 200, other_created.text
    other_id = other_created.json()["data"]["resource_id"]

    force_session_cookie(authz_client, issued.cookie_value)
    mixed = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": self_id,
                    "owner_user_id": str(other_user.id),
                    "lifecycle_status": "active",
                },
                {
                    "resource_id": other_id,
                    "owner_user_id": str(user.id),
                    "lifecycle_status": "active",
                },
            ]
        },
        headers=authz_headers(issued, with_csrf=False),
    )
    assert mixed.status_code == 200, mixed.text
    data = mixed.json()["data"]
    assert data["excluded_count"] == 1
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["resource_id"] == other_id
    assert data["candidates"][0]["owner_user_id"] == str(other_user.id)

    only_self = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": self_id,
                    "owner_user_id": str(other_user.id),
                    "lifecycle_status": "active",
                }
            ]
        },
        headers=authz_headers(issued, with_csrf=False),
    )
    assert only_self.status_code == 404
    assert only_self.json()["code"] == "NO_ROUTE_CANDIDATE"


def test_relabel_disabled_as_active_uses_server_state(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
    auth_migrated_postgres: str,
) -> None:
    buyer = account_factory.create_active(role=UserRole.buyer, nickname="买家")
    seller = account_factory.create_active(role=UserRole.seller, nickname="卖家")
    s_sess = authz_sessions.issue(seller)
    force_session_cookie(authz_client, s_sess.cookie_value)
    created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "seller_key", "action": "seller_key.register"},
        headers=authz_headers(s_sess),
    )
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["resource_id"]

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE resource_ownerships SET lifecycle_status = 'disabled' "
                    "WHERE resource_id = CAST(:id AS uuid)"
                ),
                {"id": rid},
            )
    finally:
        engine.dispose()

    b_sess = authz_sessions.issue(buyer)
    force_session_cookie(authz_client, b_sess.cookie_value)
    relabeled = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": rid,
                    "owner_user_id": str(seller.id),
                    "lifecycle_status": "active",
                }
            ]
        },
        headers=authz_headers(b_sess, with_csrf=False),
    )
    assert relabeled.status_code == 404
    assert relabeled.json()["code"] == "NO_ROUTE_CANDIDATE"
