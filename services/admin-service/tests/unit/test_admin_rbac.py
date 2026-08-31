from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.admin import ADMIN_COOKIE, USER_COOKIE, AdminError, AdminService
from app.domain.admin.rbac import NEVER, ROLES, evaluate

ACTIONS = [
    "user.lookup",
    "user.force_logout",
    "connection.view_health",
    "connection.replace_dedicated",
    "price.publish",
    "price.read",
    "route.rollback",
    "route.read",
    "ledger.reverse",
    "ledger.read",
    "ledger.edit_balance",
    "credential.read",
    "audit.read",
    "audit.delete",
    "break_glass",
    "project.lookup",
    "alert.read",
]


def test_rbac_matrix_every_combination() -> None:
    expected_allow = {
        ("support", False, "user.lookup"),
        ("support", False, "user.force_logout"),
        ("support", False, "audit.read"),
        ("support", True, "user.lookup"),
        ("support", True, "audit.read"),
        ("supply_ops", False, "connection.view_health"),
        ("supply_ops", False, "connection.replace_dedicated"),
        ("supply_ops", True, "connection.view_health"),
        ("pricing", False, "price.publish"),
        ("pricing", False, "route.rollback"),
        ("ledger", False, "ledger.reverse"),
        ("ledger", False, "ledger.read"),
        ("ledger", False, "alert.read"),
        ("ledger", True, "ledger.read"),
        ("ledger", True, "alert.read"),
        ("pricing", False, "price.read"),
        ("pricing", False, "route.read"),
        ("pricing", False, "alert.read"),
        ("pricing", True, "price.read"),
        ("pricing", True, "route.read"),
        ("pricing", True, "alert.read"),
        ("support", False, "project.lookup"),
        ("support", False, "alert.read"),
        ("support", True, "project.lookup"),
        ("support", True, "alert.read"),
        ("supply_ops", False, "project.lookup"),
        ("supply_ops", False, "alert.read"),
        ("supply_ops", True, "project.lookup"),
        ("supply_ops", True, "alert.read"),
        ("security_audit", False, "audit.read"),
        ("security_audit", False, "user.force_logout"),
        ("security_audit", False, "user.lookup"),
        ("security_audit", False, "connection.view_health"),
        ("security_audit", False, "break_glass"),
        ("security_audit", False, "project.lookup"),
        ("security_audit", False, "alert.read"),
        ("security_audit", True, "audit.read"),
        ("security_audit", True, "user.lookup"),
        ("security_audit", True, "connection.view_health"),
        ("security_audit", True, "project.lookup"),
        ("security_audit", True, "alert.read"),
    }
    for role in ROLES:
        for readonly in (False, True):
            for action in ACTIONS:
                allowed = evaluate(role, readonly, action)
                key = (role, readonly, action)
                if action in NEVER:
                    assert allowed is False
                elif key in expected_allow:
                    assert allowed is True, key
                else:
                    assert allowed is False, key


def _svc() -> AdminService:
    return AdminService()


def test_user_cookie_never_opens_admin() -> None:
    svc = _svc()
    svc.seed(login="ops", password="pw", role="support")
    with pytest.raises(AdminError) as exc:
        svc.login(
            login="ops",
            password="pw",
            mfa_code="totp-ok",
            user_cookie="user-session",
        )
    assert exc.value.code == "USER_SESSION_REJECTED"
    sess, token = svc.login(login="ops", password="pw", mfa_code="totp-ok")
    assert sess.admin_id
    header = svc.cookie_header(token)
    assert ADMIN_COOKIE in header
    assert USER_COOKIE not in header
    assert "Path=/admin" in header
    with pytest.raises(AdminError) as again:
        svc.resolve(admin_token=token, user_cookie="user-session")
    assert again.value.code == "USER_SESSION_REJECTED"


def test_cannot_promote_buyer() -> None:
    svc = _svc()
    with pytest.raises(AdminError) as exc:
        svc.promote_user("buyer-1", "support")
    assert exc.value.code == "PROMOTION_DENIED"


def test_high_risk_requires_mfa_step_up_and_reason() -> None:
    clock = {"t": datetime(2026, 8, 31, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["t"]

    svc = AdminService(now=now)
    svc.seed(login="fin", password="pw", role="ledger", mfa_enrolled=True)
    _, token = svc.login(login="fin", password="pw", mfa_code="totp-ok")
    with pytest.raises(AdminError) as reason:
        svc.execute(
            admin_token=token,
            user_cookie=None,
            action="ledger.reverse",
            target="r1",
            reason="",
            request_id="req-1",
        )
    assert reason.value.code == "REASON_REQUIRED"
    with pytest.raises(AdminError) as step:
        svc.execute(
            admin_token=token,
            user_cookie=None,
            action="ledger.reverse",
            target="r1",
            reason="fix",
            request_id="req-1",
        )
    assert step.value.code == "STEP_UP_REQUIRED"
    svc.step_up(admin_token=token, mfa_code="totp-ok")
    out = svc.execute(
        admin_token=token,
        user_cookie=None,
        action="ledger.reverse",
        target="r1",
        reason="vendor mismatch",
        request_id="req-1",
        before={"token": "abc", "balance": 10},
        after={"balance": 8},
    )
    assert out["result"] == "ok"
    rec = svc.audit.list()[-1]
    assert rec.before["token"] == "[redacted]"
    assert rec.before["balance"] == 10
    clock["t"] = clock["t"] + timedelta(minutes=6)
    with pytest.raises(AdminError) as expired:
        svc.execute(
            admin_token=token,
            user_cookie=None,
            action="ledger.reverse",
            target="r2",
            reason="again",
            request_id="req-2",
        )
    assert expired.value.code == "STEP_UP_REQUIRED"


def test_never_actions_and_readonly_denied() -> None:
    svc = _svc()
    svc.seed(login="pr", password="pw", role="pricing", readonly=True)
    _, token = svc.login(login="pr", password="pw", mfa_code="totp-ok")
    svc.step_up(admin_token=token, mfa_code="totp-ok")
    with pytest.raises(AdminError) as pub:
        svc.execute(
            admin_token=token,
            user_cookie=None,
            action="price.publish",
            target="rv-1",
            reason="ship",
            request_id="r",
        )
    assert pub.value.code == "FORBIDDEN"
    for action in ("credential.read", "ledger.edit_balance", "audit.delete"):
        with pytest.raises(AdminError) as never:
            svc.execute(
                admin_token=token,
                user_cookie=None,
                action=action,
                target="x",
                reason="no",
                request_id="r",
            )
        assert never.value.code == "FORBIDDEN"


def test_audit_immutable_and_chain() -> None:
    svc = _svc()
    svc.seed(login="sec", password="pw", role="security_audit")
    _, token = svc.login(login="sec", password="pw", mfa_code="totp-ok")
    svc.execute(
        admin_token=token,
        user_cookie=None,
        action="audit.read",
        target="*",
        reason="",
        request_id="r",
    )
    event_id = svc.audit.list()[0].event_id
    with pytest.raises(AdminError) as mut:
        svc.audit.mutate(event_id)
    assert mut.value.code == "IMMUTABLE_AUDIT"
    with pytest.raises(AdminError) as deleted:
        svc.audit.delete(event_id)
    assert deleted.value.code == "IMMUTABLE_AUDIT"
    assert svc.audit.verify_chain() is True


def test_break_glass_alerts_and_closes() -> None:
    alerts: list[str] = []
    svc = AdminService(alert=alerts.append)
    svc.seed(login="sec", password="pw", role="security_audit")
    _, token = svc.login(login="sec", password="pw", mfa_code="totp-ok")
    svc.step_up(admin_token=token, mfa_code="totp-ok")
    out = svc.execute(
        admin_token=token,
        user_cookie=None,
        action="break_glass",
        target="prod",
        reason="incident-1",
        request_id="bg",
    )
    assert out["alerted"] is True
    assert alerts
    case = svc.close_break_glass(
        admin_token=token, case_id=out["break_glass_id"], review="reviewed"
    )
    assert case.closed_at is not None
    assert case.review == "reviewed"
