"""Ownership lifecycle changes affect route candidates immediately."""

from __future__ import annotations

import uuid

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


def test_disabled_ownership_excluded_from_route(
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

    b_sess = authz_sessions.issue(buyer)
    force_session_cookie(authz_client, b_sess.cookie_value)
    ok = authz_client.post(
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
    assert ok.status_code == 200

    # Disable ownership fact in DB
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

    # Client must pass updated lifecycle; server filter still drops non-active
    blocked = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": rid,
                    "owner_user_id": str(seller.id),
                    "lifecycle_status": "disabled",
                }
            ]
        },
        headers=authz_headers(b_sess, with_csrf=False),
    )
    assert blocked.status_code == 404
    assert blocked.json()["code"] == "NO_ROUTE_CANDIDATE"
