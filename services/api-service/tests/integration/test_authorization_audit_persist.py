"""Audit events queryable by request_id after deny / state change."""

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


def test_deny_and_create_leave_audit_rows(
    authz_client: TestClient,
    account_factory,
    authz_sessions: AuthzSessionFactory,
    auth_migrated_postgres: str,
) -> None:
    buyer = account_factory.create_active(role=UserRole.buyer, nickname="审计买家")
    issued = authz_sessions.issue(buyer)
    force_session_cookie(authz_client, issued.cookie_value)

    deny_rid = "audit-deny-1"
    denied = authz_client.post(
        "/api/v1/authorization/evaluate",
        json={"action": "seller_key.register"},
        headers={**authz_headers(issued, with_csrf=False), "X-Request-ID": deny_rid},
    )
    assert denied.status_code == 403

    create_rid = "audit-create-1"
    created = authz_client.post(
        "/api/v1/authorization/fixtures/resources",
        json={"resource_type": "proxy_key", "action": "proxy_key.create"},
        headers={**authz_headers(issued), "X-Request-ID": create_rid},
    )
    assert created.status_code == 200, created.text

    engine = create_engine(auth_migrated_postgres, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            deny_rows = conn.execute(
                text(
                    "SELECT action, reason_code, session_id, safe_metadata "
                    "FROM authorization_security_events WHERE request_id = :r"
                ),
                {"r": deny_rid},
            ).fetchall()
            create_rows = conn.execute(
                text(
                    "SELECT action, outcome, session_id "
                    "FROM authorization_security_events WHERE request_id = :r"
                ),
                {"r": create_rid},
            ).fetchall()
        assert len(deny_rows) >= 1
        assert deny_rows[0][0] == "seller_key.register"
        assert deny_rows[0][1] == "ROLE_DENIED"
        assert deny_rows[0][2] is not None  # session_id populated
        blob = str(deny_rows).lower()
        assert "password" not in blob
        assert "api_key" not in blob
        assert len(create_rows) >= 1
        assert create_rows[0][2] is not None
    finally:
        engine.dispose()
