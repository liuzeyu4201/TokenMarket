from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.admin import ADMIN_COOKIE, USER_COOKIE, AdminService
from app.main import app


def test_admin_login_isolated_from_user_cookie() -> None:
    svc = AdminService()
    svc.seed(login="ops", password="pw", role="support")
    client = TestClient(app)
    client.__enter__()
    client.app.state.admin_service = svc
    try:
        denied = client.post(
            "/admin/v1/sessions",
            json={"login": "ops", "password": "pw", "mfa_code": "totp-ok"},
            cookies={USER_COOKIE: "user-token"},
        )
        assert denied.status_code == 401
        assert denied.json()["code"] == "USER_SESSION_REJECTED"
        ok = client.post(
            "/admin/v1/sessions",
            json={"login": "ops", "password": "pw", "mfa_code": "totp-ok"},
        )
        assert ok.status_code == 200, ok.text
        cookie = ok.headers.get("set-cookie", "") + str(ok.headers)
        assert ADMIN_COOKIE in cookie
        token = ok.cookies.get(ADMIN_COOKIE)
        if token:
            forbidden = client.post(
                "/admin/v1/actions",
                json={"action": "price.publish", "target": "rv", "reason": "x"},
                cookies={ADMIN_COOKIE: token},
            )
            assert forbidden.status_code == 403
    finally:
        client.__exit__(None, None, None)
