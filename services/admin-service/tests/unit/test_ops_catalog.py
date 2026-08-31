from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.admin import AdminError, AdminService
from app.domain.ops.catalog import CONNECTION_TOTAL, MAX_LIMIT, OpsCatalog
from app.domain.ops.pipeline import ConfigPipeline
from app.domain.ops.wizard import WizardService

SECRET_MARKERS = ("sk-", "api_key", "plaintext", "BEGIN PRIVATE", "password")


def test_connection_list_is_server_paginated() -> None:
    cat = OpsCatalog()
    page = cat.list_page("connection", cursor="", limit=50)
    assert page.total == CONNECTION_TOTAL == 100_000
    assert len(page.items) == 50
    assert page.next_cursor == "50"
    huge = cat.list_page("connection", cursor="", limit=100_000)
    assert len(huge.items) <= MAX_LIMIT
    tail = cat.list_page("connection", cursor="99950", limit=50)
    assert len(tail.items) == 50
    assert tail.next_cursor is None
    assert not hasattr(cat, "_rows") or len(getattr(cat, "_rows")) < 1_000
    blob = json.dumps(page.items)
    for marker in SECRET_MARKERS:
        assert marker not in blob


def test_export_and_detail_never_include_secrets() -> None:
    cat = OpsCatalog()
    cat.poison(
        "connection",
        "conn-000000",
        {"api_key": "sk-live-xxx", "plaintext": "secret-value"},
    )
    exported = cat.export("connection", "conn-000000")
    blob = json.dumps(exported)
    for marker in SECRET_MARKERS:
        assert marker not in blob
    assert "fingerprint" in exported
    assert "health" in exported
    detail = cat.get("connection", "conn-000000")
    dblob = json.dumps(detail)
    for marker in SECRET_MARKERS:
        assert marker not in dblob
    assert "audit" in detail
    assert "alerts" in detail
    assert "related" in detail
    assert "version" in detail


def test_stale_health_is_unknown_not_live() -> None:
    clock = {"t": datetime(2026, 8, 31, tzinfo=timezone.utc)}
    cat = OpsCatalog(now=lambda: clock["t"])
    cat.mark_probe("conn-000001", clock["t"] - timedelta(hours=2))
    item = cat.get("connection", "conn-000001")["item"]
    assert item["freshness"] in {"stale", "unknown"}
    assert item["health"] == "unknown"
    assert item["freshness"] != "live"
    assert item["health"] != "healthy"


def test_patch_active_rejected_and_simulate_fail_keeps_active() -> None:
    pipe = ConfigPipeline()
    before = pipe.active_version("price")
    with pytest.raises(AdminError) as patch:
        pipe.patch_active("price", {"buyer_bps": 1})
    assert patch.value.code == "PATCH_ACTIVE_DENIED"
    assert pipe.active_version("price") == before
    draft = pipe.create_draft(
        "price",
        {"buyer_bps": 100, "seller_max_bps": 8000, "invalid": True},
    )
    sim = pipe.simulate(draft.draft_id)
    assert sim["ok"] is False
    with pytest.raises(AdminError) as pub:
        pipe.publish(draft.draft_id)
    assert pub.value.code in {"SIMULATE_FAILED", "APPROVAL_REQUIRED"}
    assert pipe.active_version("price") == before
    good = pipe.create_draft("price", {"buyer_bps": 9500, "seller_max_bps": 8000})
    assert pipe.diff(good.draft_id)["changes"]
    assert pipe.simulate(good.draft_id)["ok"] is True
    pipe.approve(good.draft_id)
    published = pipe.publish(good.draft_id)
    assert published["version"] != before
    assert pipe.active_version("price") != before


def test_wizard_cancel_and_timeout_leave_no_success_audit() -> None:
    clock = {"t": datetime(2026, 8, 31, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["t"]

    svc = AdminService(now=now)
    svc.seed(login="sup", password="pw", role="support")
    _, token = svc.login(login="sup", password="pw", mfa_code="totp-ok")
    wiz = WizardService(now=now)
    pending = wiz.start(kind="force_logout", target="sess-9", reason="abuse")
    assert pending.status == "pending"
    assert pending.impact
    wiz.cancel(pending.wizard_id)
    with pytest.raises(AdminError) as cancelled:
        wiz.confirm(
            pending.wizard_id,
            admin=svc,
            admin_token=token,
            user_cookie=None,
            request_id="r-cancel",
            reason="abuse",
        )
    assert cancelled.value.code == "WIZARD_CANCELLED"
    assert all(not (r.action == "user.force_logout" and r.result == "ok") for r in svc.audit.list())

    other = wiz.start(kind="force_logout", target="sess-8", reason="idle")
    clock["t"] = clock["t"] + timedelta(minutes=10)
    with pytest.raises(AdminError) as expired:
        wiz.confirm(
            other.wizard_id,
            admin=svc,
            admin_token=token,
            user_cookie=None,
            request_id="r-exp",
            reason="idle",
        )
    assert expired.value.code == "WIZARD_EXPIRED"
    assert all(not (r.action == "user.force_logout" and r.result == "ok") for r in svc.audit.list())


def test_other_kinds_search_and_unknown() -> None:
    cat = OpsCatalog()
    for kind in (
        "user",
        "session",
        "project",
        "price",
        "route",
        "ledger",
        "alert",
        "audit",
    ):
        page = cat.list_page(kind, limit=2)
        assert len(page.items) == 2
        detail = cat.get(kind, page.items[0]["id"])
        assert detail["item"]["id"] == page.items[0]["id"]
        exported = cat.export(kind, page.items[0]["id"])
        assert "id" in exported
    found = cat.list_page("connection", q="conn-000002")
    assert found.items[0]["id"] == "conn-000002"
    empty = cat.list_page("connection", q="no-such")
    assert empty.items == []
    with pytest.raises(AdminError):
        cat.get("connection", "nope")
    with pytest.raises(AdminError):
        cat.list_page("nope")
    with pytest.raises(AdminError):
        cat.list_page("connection", cursor="x")


def test_wizard_confirm_records_request_id() -> None:
    svc = AdminService()
    svc.seed(login="sup", password="pw", role="support")
    _, token = svc.login(login="sup", password="pw", mfa_code="totp-ok")
    svc.step_up(admin_token=token, mfa_code="totp-ok")
    wiz = WizardService()
    pending = wiz.start(kind="force_logout", target="sess-1", reason="compromise")
    out = wiz.confirm(
        pending.wizard_id,
        admin=svc,
        admin_token=token,
        user_cookie=None,
        request_id="req-wiz-1",
        reason="compromise",
    )
    assert out.status == "confirmed"
    assert out.request_id == "req-wiz-1"
    rec = svc.audit.list()[-1]
    assert rec.request_id == "req-wiz-1"
    assert rec.action == "user.force_logout"
    assert rec.result == "ok"
