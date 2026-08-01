"""IDOR: cross-user resource access is indistinguishable not-found."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.domain.users.models import UserRole
from tests.integration.conftest_authorization import (
    AuthzSessionFactory,
    authz_headers,
    force_session_cookie,
)

pytestmark = pytest.mark.integration


def test_cross_user_read_and_patch_are_404(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    owner = account_factory.create_active(role=UserRole.seller, nickname="所有者")
    stranger = account_factory.create_active(role=UserRole.seller, nickname="外人")
    o_sess = authz_sessions.issue(owner)
    force_session_cookie(authz_client, o_sess.cookie_value)
    created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "seller_key", "action": "seller_key.register"},
        headers=authz_headers(o_sess),
    )
    assert created.status_code == 200, created.text
    resource_id = created.json()["data"]["resource_id"]

    s_sess = authz_sessions.issue(stranger)
    force_session_cookie(authz_client, s_sess.cookie_value)
    missing = str(uuid.uuid4())
    cross = authz_client.get(
        f"/api/v1/authorization/fixtures/resources/seller_key/{resource_id}",
        headers=authz_headers(s_sess, with_csrf=False),
    )
    ghost = authz_client.get(
        f"/api/v1/authorization/fixtures/resources/seller_key/{missing}",
        headers=authz_headers(s_sess, with_csrf=False),
    )
    assert cross.status_code == ghost.status_code == 404
    assert cross.json()["code"] == ghost.json()["code"] == "RESOURCE_NOT_FOUND"

    patch = authz_client.patch(
        f"/api/v1/authorization/fixtures/resources/seller_key/{resource_id}",
        json={"action": "seller_key.disable"},
        headers=authz_headers(s_sess),
    )
    assert patch.status_code == 404
    assert patch.json()["code"] == "RESOURCE_NOT_FOUND"
