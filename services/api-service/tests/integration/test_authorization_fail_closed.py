"""DB unavailable → evaluate returns 503 fail-closed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.users.models import UserRole
from app.main import app
from tests.integration.conftest_authorization import (
    AuthzSessionFactory,
    _authz_env,
    authz_headers,
    force_session_cookie,
)

pytestmark = pytest.mark.integration


def test_evaluate_without_session_factory_is_503(
    auth_migrated_postgres: str,
    account_factory,
    authz_sessions: AuthzSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authz_env(monkeypatch, auth_migrated_postgres)
    user = account_factory.create_active(role=UserRole.buyer)
    issued = authz_sessions.issue(user)
    with TestClient(app) as client:
        # Drop session factory after lifespan init
        client.app.state.session_factory = None
        force_session_cookie(client, issued.cookie_value)
        res = client.post(
            "/api/v1/authorization/evaluate",
            json={"action": "proxy_key.create"},
            headers=authz_headers(issued, with_csrf=False),
        )
        assert res.status_code == 503
        assert res.json()["code"] == "SERVICE_UNAVAILABLE"
