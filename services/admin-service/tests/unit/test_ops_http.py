from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.admin import ADMIN_COOKIE, AdminService
from app.domain.ops import ConfigPipeline, OpsCatalog, WizardService
from app.main import app


def _token(response) -> str:  # type: ignore[no-untyped-def]
    raw = response.headers.get("set-cookie", "")
    for part in raw.split(";"):
        if ADMIN_COOKIE in part and "=" in part:
            return part.split("=", 1)[1].strip()
    got = response.cookies.get(ADMIN_COOKIE)
    assert got
    return str(got)


def _client(role: str = "supply_ops", readonly: bool = False) -> tuple[TestClient, str]:
    svc = AdminService()
    svc.seed(login="ops", password="pw", role=role, readonly=readonly)
    client = TestClient(app)
    client.__enter__()
    client.app.state.admin_service = svc
    client.app.state.ops_catalog = OpsCatalog()
    client.app.state.config_pipeline = ConfigPipeline()
    client.app.state.wizard_service = WizardService()
    ok = client.post(
        "/admin/v1/sessions",
        json={"login": "ops", "password": "pw", "mfa_code": "totp-ok"},
    )
    assert ok.status_code == 200, ok.text
    token = _token(ok)
    client.cookies.set(ADMIN_COOKIE, token)
    return client, token


def test_ops_list_paginated_and_export_has_no_secret() -> None:
    client, _token_value = _client("supply_ops")
    try:
        page = client.get("/admin/v1/ops/connection", params={"limit": 50})
        assert page.status_code == 200, page.text
        data = page.json()["data"]
        assert len(data["items"]) == 50
        assert data["total"] == 100000
        assert data["next_cursor"] == "50"
        dumped = client.get("/admin/v1/ops/connection", params={"limit": 100000})
        assert len(dumped.json()["data"]["items"]) <= 100
        item_id = data["items"][0]["id"]
        exported = client.get(f"/admin/v1/ops/connection/{item_id}/export")
        assert exported.status_code == 200
        body = exported.text.lower()
        assert "sk-" not in body
        assert "api_key" not in body
        assert "plaintext" not in body
        assert "fingerprint" in body
        ledger = client.get("/admin/v1/ops/price")
        assert ledger.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_ledger_readonly_cannot_publish_price() -> None:
    client, _token_value = _client("ledger", readonly=True)
    try:
        denied = client.post(
            "/admin/v1/config",
            json={"kind": "price", "payload": {"buyer_bps": 9000}},
        )
        assert denied.status_code == 403
        listed = client.get("/admin/v1/ops/ledger")
        assert listed.status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_patch_active_and_forbidden_editors() -> None:
    client, token = _client("pricing")
    try:
        step = client.post(
            "/admin/v1/step-up",
            json={"mfa_code": "totp-ok"},
            cookies={ADMIN_COOKIE: token},
        )
        assert step.status_code == 200, step.text
        patch = client.patch("/admin/v1/config/active", json={"buyer_bps": 1})
        assert patch.status_code == 409
        assert patch.json()["code"] == "PATCH_ACTIVE_DENIED"
        sql = client.post("/admin/v1/sql", json={"q": "select 1"})
        assert sql.status_code == 403
        assert sql.json()["code"] == "SQL_EDITOR_DENIED"
        bal = client.patch("/admin/v1/ledger/led-1/balance", json={"amount": 0})
        assert bal.status_code == 403
        gone = client.delete("/admin/v1/audit/evt-1")
        assert gone.status_code == 409
        draft = client.post(
            "/admin/v1/config",
            json={
                "kind": "price",
                "payload": {
                    "buyer_bps": 100,
                    "seller_max_bps": 8000,
                    "invalid": True,
                },
            },
        )
        assert draft.status_code == 200, draft.text
        draft_id = draft.json()["data"]["draft_id"]
        sim = client.post(f"/admin/v1/config/{draft_id}/simulate")
        assert sim.json()["data"]["ok"] is False
        before = client.get("/admin/v1/ops/price").json()["data"]
        pub = client.post(
            f"/admin/v1/config/{draft_id}/publish",
            json={"reason": "ship"},
        )
        assert pub.status_code == 409
        after = client.get("/admin/v1/ops/price").json()["data"]
        assert after["items"][0]["version"] == before["items"][0]["version"]
    finally:
        client.__exit__(None, None, None)


def test_publish_and_rollback_http() -> None:
    client, _token_value = _client("pricing")
    try:
        me = client.get("/admin/v1/session")
        assert me.status_code == 200
        assert me.json()["data"]["role"] == "pricing"
        kinds = client.get("/admin/v1/ops")
        assert kinds.status_code == 200
        assert "price" in kinds.json()["data"]["kinds"]
        step = client.post("/admin/v1/step-up", json={"mfa_code": "totp-ok"})
        assert step.status_code == 200
        draft = client.post(
            "/admin/v1/config",
            json={
                "kind": "price",
                "payload": {"buyer_bps": 9500, "seller_max_bps": 8000},
            },
        )
        assert draft.status_code == 200, draft.text
        draft_id = draft.json()["data"]["draft_id"]
        got = client.get(f"/admin/v1/config/{draft_id}")
        assert got.status_code == 200
        diff = client.get(f"/admin/v1/config/{draft_id}/diff")
        assert diff.status_code == 200
        sim = client.post(f"/admin/v1/config/{draft_id}/simulate")
        assert sim.json()["data"]["ok"] is True
        appr = client.post(f"/admin/v1/config/{draft_id}/approve")
        assert appr.status_code == 200
        pub = client.post(
            f"/admin/v1/config/{draft_id}/publish",
            json={"reason": "ship"},
        )
        assert pub.status_code == 200, pub.text
        assert pub.json()["data"]["version"] == 2
        rb = client.post(
            "/admin/v1/config/price/rollback",
            json={"to_version": 1, "reason": "revert"},
        )
        assert rb.status_code == 200
        detail = client.get("/admin/v1/ops/price/price-000000")
        assert detail.status_code == 200
        assert "audit" in detail.json()["data"]
    finally:
        client.__exit__(None, None, None)


def test_wizard_http_cancel_does_not_execute() -> None:
    client, _token_value = _client("support")
    try:
        started = client.post(
            "/admin/v1/wizards",
            json={"kind": "force_logout", "target": "sess-1", "reason": "abuse"},
        )
        assert started.status_code == 200, started.text
        wizard_id = started.json()["data"]["wizard_id"]
        cancel = client.post(f"/admin/v1/wizards/{wizard_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["data"]["status"] == "cancelled"
        confirm = client.post(
            f"/admin/v1/wizards/{wizard_id}/confirm",
            json={"reason": "abuse"},
        )
        assert confirm.status_code == 409
        assert confirm.json()["code"] == "WIZARD_CANCELLED"
    finally:
        client.__exit__(None, None, None)
