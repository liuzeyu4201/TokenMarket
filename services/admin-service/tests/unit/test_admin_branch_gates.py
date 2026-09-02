"""Branch coverage for admin RBAC, redaction, and identity fail-closed paths."""

from __future__ import annotations

import pytest

from app.domain.admin import AdminError, AdminService
from app.domain.admin.rbac import evaluate
from app.domain.admin.redact import redact


def test_evaluate_unknown_role_denied() -> None:
    assert evaluate("not-a-role", False, "audit.read") is False


def test_redact_nested_list_and_secret_strings() -> None:
    payload = {
        "items": [{"note": "ok"}, {"api_key": "k"}],
        "blob": "token=abc",
        "sk": "sk-live-1",
        "plain": "hello",
    }
    out = redact(payload)
    assert out["items"][0]["note"] == "ok"
    assert out["items"][1]["api_key"] == "[redacted]"
    assert out["blob"] == "[redacted]"
    assert out["sk"] == "[redacted]"
    assert out["plain"] == "hello"


def test_seed_invalid_role_and_login_failures() -> None:
    svc = AdminService()
    with pytest.raises(AdminError) as role:
        svc.seed(login="x", password="pw", role="superuser")
    assert role.value.code == "VALIDATION"
    svc.seed(login="ops", password="pw", role="support")
    with pytest.raises(AdminError) as missing:
        svc.login(login="nope", password="pw", mfa_code="totp-ok")
    assert missing.value.code == "UNAUTHORIZED"
    with pytest.raises(AdminError) as bad_pw:
        svc.login(login="ops", password="wrong", mfa_code="totp-ok")
    assert bad_pw.value.code == "UNAUTHORIZED"
    with pytest.raises(AdminError) as mfa:
        svc.login(login="ops", password="pw", mfa_code="bad")
    assert mfa.value.code == "MFA_REQUIRED"


def test_logout_and_resolve_missing_token() -> None:
    svc = AdminService()
    svc.seed(login="ops", password="pw", role="support")
    _, token = svc.login(login="ops", password="pw", mfa_code="totp-ok")
    svc.logout(None)
    svc.logout("")
    with pytest.raises(AdminError) as missing:
        svc.resolve(admin_token=None, user_cookie=None)
    assert missing.value.code == "UNAUTHORIZED"
    with pytest.raises(AdminError) as bogus:
        svc.resolve(admin_token="nope", user_cookie=None)
    assert bogus.value.code == "UNAUTHORIZED"
    svc.logout(token)
    with pytest.raises(AdminError) as gone:
        svc.resolve(admin_token=token, user_cookie=None)
    assert gone.value.code == "UNAUTHORIZED"


def test_step_up_and_ensure_action_denials() -> None:
    svc = AdminService()
    svc.seed(login="fin", password="pw", role="ledger", mfa_enrolled=True)
    _, token = svc.login(login="fin", password="pw", mfa_code="totp-ok")
    with pytest.raises(AdminError) as mfa:
        svc.step_up(admin_token=token, mfa_code="bad")
    assert mfa.value.code == "MFA_REQUIRED"
    with pytest.raises(AdminError) as forbidden:
        svc.ensure_action(
            admin_token=token,
            user_cookie=None,
            action="price.publish",
            reason="no",
            audit_denial=True,
            request_id="r",
        )
    assert forbidden.value.code == "FORBIDDEN"
    assert svc.audit.list()[-1].result == "denied"
    svc.seed(
        login="plain",
        password="pw",
        role="ledger",
        mfa_enrolled=False,
    )
    _, no_mfa = svc.login(login="plain", password="pw", mfa_code="")
    with pytest.raises(AdminError) as need_mfa:
        svc.ensure_action(
            admin_token=no_mfa,
            user_cookie=None,
            action="ledger.reverse",
            reason="fix",
        )
    assert need_mfa.value.code == "MFA_REQUIRED"


def test_close_break_glass_unknown_and_readonly() -> None:
    svc = AdminService()
    svc.seed(login="sec", password="pw", role="security_audit")
    _, token = svc.login(login="sec", password="pw", mfa_code="totp-ok")
    with pytest.raises(AdminError) as missing:
        svc.close_break_glass(admin_token=token, case_id="nope", review="x")
    assert missing.value.code == "VALIDATION"
    svc.seed(
        login="ro",
        password="pw",
        role="security_audit",
        readonly=True,
    )
    _, ro = svc.login(login="ro", password="pw", mfa_code="totp-ok")
    svc.step_up(admin_token=token, mfa_code="totp-ok")
    opened = svc.execute(
        admin_token=token,
        user_cookie=None,
        action="break_glass",
        target="prod",
        reason="inc",
        request_id="bg",
    )
    with pytest.raises(AdminError) as forbidden:
        svc.close_break_glass(
            admin_token=ro,
            case_id=opened["break_glass_id"],
            review="no",
        )
    assert forbidden.value.code == "FORBIDDEN"


def test_audit_chain_detects_tamper() -> None:
    svc = AdminService()
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
    rec = svc.audit.list()[0]
    rec.record_hash = "deadbeef"
    assert svc.audit.verify_chain() is False
