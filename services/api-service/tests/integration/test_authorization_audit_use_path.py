"""proxy_key.use allow path must not write per-request security events."""

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


def test_use_allow_no_security_event(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
    auth_migrated_postgres: str,
) -> None:
    buyer = account_factory.create_active(role=UserRole.buyer, nickname="高频")
    issued = authz_sessions.issue(buyer)
    force_session_cookie(authz_client, issued.cookie_value)
    created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "proxy_key", "action": "proxy_key.create"},
        headers=authz_headers(issued),
    )
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["resource_id"]

    use_rid = "use-no-audit"
    use = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={
            "action": "proxy_key.use",
            "resource_type": "proxy_key",
            "resource_id": rid,
        },
        headers={**authz_headers(issued, with_csrf=False), "X-Request-ID": use_rid},
    )
    assert use.status_code == 200, use.text

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            n = conn.execute(
                text(
                    "SELECT COUNT(*) FROM authorization_security_events "
                    "WHERE request_id = :r"
                ),
                {"r": use_rid},
            ).scalar_one()
        assert int(n) == 0
    finally:
        engine.dispose()
