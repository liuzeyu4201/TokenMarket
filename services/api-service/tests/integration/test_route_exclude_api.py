"""HTTP self-route exclusion endpoint."""

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


def test_exclude_self_http(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
) -> None:
    user = account_factory.create_active(role=UserRole.both, nickname="路由")
    other = uuid.uuid4()
    issued = authz_sessions.issue(user)
    force_session_cookie(authz_client, issued.cookie_value)

    mixed = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": str(uuid.uuid4()),
                    "owner_user_id": str(user.id),
                    "lifecycle_status": "active",
                },
                {
                    "resource_id": str(uuid.uuid4()),
                    "owner_user_id": str(other),
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
    assert data["candidates"][0]["owner_user_id"] == str(other)

    only_self = authz_client.post(
        "/api/v1/authorization/route-candidates/exclude-self",
        json={
            "candidates": [
                {
                    "resource_id": str(uuid.uuid4()),
                    "owner_user_id": str(user.id),
                    "lifecycle_status": "active",
                }
            ]
        },
        headers=authz_headers(issued, with_csrf=False),
    )
    assert only_self.status_code == 404
    assert only_self.json()["code"] == "NO_ROUTE_CANDIDATE"
