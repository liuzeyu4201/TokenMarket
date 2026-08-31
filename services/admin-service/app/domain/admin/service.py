"""Isolated admin identity, RBAC enforcement, and high-risk actions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.domain.admin.audit import AuditLog
from app.domain.admin.errors import (
    ADMIN_COOKIE,
    ADMIN_COOKIE_PATH,
    FORBIDDEN,
    MFA_REQUIRED,
    MSG,
    PROMOTION_DENIED,
    REASON_REQUIRED,
    STEP_UP_REQUIRED,
    UNAUTHORIZED,
    USER_SESSION_REJECTED,
    VALIDATION,
    AdminError,
)
from app.domain.admin.rbac import HIGH_RISK, ROLES, evaluate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(secret: str, salt: str) -> str:
    raw = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), salt.encode("utf-8"), 120000
    )
    return raw.hex()


@dataclass
class AdminAccount:
    admin_id: str
    login: str
    password_salt: str
    password_digest: str
    role: str
    readonly: bool
    mfa_enrolled: bool


@dataclass
class AdminSession:
    session_id: str
    admin_id: str
    token_digest: str
    created_at: datetime
    step_up_at: datetime | None = None


@dataclass
class BreakGlassCase:
    case_id: str
    actor_id: str
    reason: str
    alerted: bool
    opened_at: datetime
    closed_at: datetime | None = None
    review: str = ""


class AdminService:
    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        alert: Callable[[str], None] | None = None,
        step_up_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._now = now or _now
        self._alert = alert
        self._ttl = step_up_ttl
        self._admins: dict[str, AdminAccount] = {}
        self._by_login: dict[str, str] = {}
        self._sessions: dict[str, AdminSession] = {}
        self._tokens: dict[str, str] = {}
        self.audit = AuditLog()
        self.alerts: list[str] = []
        self.break_glass: dict[str, BreakGlassCase] = {}
        self._pepper = "admin-identity-v1"

    def seed(
        self,
        *,
        login: str,
        password: str,
        role: str,
        readonly: bool = False,
        mfa_enrolled: bool = True,
    ) -> AdminAccount:
        if role not in ROLES:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        salt = secrets.token_hex(8)
        acc = AdminAccount(
            admin_id=str(uuid.uuid4()),
            login=login,
            password_salt=salt,
            password_digest=_digest(password, salt + self._pepper),
            role=role,
            readonly=readonly,
            mfa_enrolled=mfa_enrolled,
        )
        self._admins[acc.admin_id] = acc
        self._by_login[login] = acc.admin_id
        return acc

    def promote_user(self, user_id: str, role: str) -> None:
        _ = (user_id, role)
        raise AdminError(PROMOTION_DENIED, MSG[PROMOTION_DENIED], http_status=403)

    def login(
        self,
        *,
        login: str,
        password: str,
        mfa_code: str,
        user_cookie: str | None = None,
    ) -> tuple[AdminSession, str]:
        if user_cookie:
            raise AdminError(
                USER_SESSION_REJECTED, MSG[USER_SESSION_REJECTED], http_status=401
            )
        admin_id = self._by_login.get(login)
        if admin_id is None:
            raise AdminError(UNAUTHORIZED, MSG[UNAUTHORIZED], http_status=401)
        acc = self._admins[admin_id]
        expected = _digest(password, acc.password_salt + self._pepper)
        if not hmac.compare_digest(expected, acc.password_digest):
            raise AdminError(UNAUTHORIZED, MSG[UNAUTHORIZED], http_status=401)
        if acc.mfa_enrolled and mfa_code != "totp-ok":
            raise AdminError(MFA_REQUIRED, MSG[MFA_REQUIRED], http_status=401)
        token = secrets.token_urlsafe(32)
        sess = AdminSession(
            session_id=str(uuid.uuid4()),
            admin_id=acc.admin_id,
            token_digest=_digest(token, self._pepper),
            created_at=self._now(),
        )
        self._sessions[sess.session_id] = sess
        self._tokens[token] = sess.session_id
        return sess, token

    def resolve(
        self, *, admin_token: str | None, user_cookie: str | None
    ) -> AdminAccount:
        if user_cookie:
            raise AdminError(
                USER_SESSION_REJECTED, MSG[USER_SESSION_REJECTED], http_status=401
            )
        if not admin_token:
            raise AdminError(UNAUTHORIZED, MSG[UNAUTHORIZED], http_status=401)
        sid = self._tokens.get(admin_token)
        if sid is None:
            raise AdminError(UNAUTHORIZED, MSG[UNAUTHORIZED], http_status=401)
        sess = self._sessions[sid]
        return self._admins[sess.admin_id]

    def step_up(self, *, admin_token: str, mfa_code: str) -> None:
        acc = self.resolve(admin_token=admin_token, user_cookie=None)
        if acc.mfa_enrolled and mfa_code != "totp-ok":
            raise AdminError(MFA_REQUIRED, MSG[MFA_REQUIRED], http_status=401)
        sid = self._tokens[admin_token]
        self._sessions[sid].step_up_at = self._now()

    def execute(
        self,
        *,
        admin_token: str | None,
        user_cookie: str | None,
        action: str,
        target: str,
        reason: str,
        request_id: str,
        source: str = "127.0.0.1",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        acc = self.resolve(admin_token=admin_token, user_cookie=user_cookie)
        if not evaluate(acc.role, acc.readonly, action):
            self.audit.append(
                actor_id=acc.admin_id,
                role=acc.role,
                action=action,
                target=target,
                reason=reason,
                request_id=request_id,
                result="denied",
                source=source,
            )
            raise AdminError(FORBIDDEN, MSG[FORBIDDEN], http_status=403)
        if action in HIGH_RISK:
            if not acc.mfa_enrolled:
                raise AdminError(MFA_REQUIRED, MSG[MFA_REQUIRED], http_status=401)
            if not str(reason).strip():
                raise AdminError(REASON_REQUIRED, MSG[REASON_REQUIRED], http_status=400)
            sid = self._tokens.get(admin_token or "")
            sess = self._sessions.get(sid or "")
            stepped = sess.step_up_at if sess else None
            if stepped is None or self._now() - stepped > self._ttl:
                raise AdminError(
                    STEP_UP_REQUIRED, MSG[STEP_UP_REQUIRED], http_status=401
                )
        rec = self.audit.append(
            actor_id=acc.admin_id,
            role=acc.role,
            action=action,
            target=target,
            reason=reason,
            request_id=request_id,
            result="ok",
            source=source,
            before=before,
            after=after,
        )
        extra: dict[str, Any] = {"audit_id": rec.event_id, "result": "ok"}
        if action == "break_glass":
            extra.update(self._open_break_glass(acc, reason))
        return extra

    def close_break_glass(
        self, *, admin_token: str, case_id: str, review: str
    ) -> BreakGlassCase:
        acc = self.resolve(admin_token=admin_token, user_cookie=None)
        case = self.break_glass.get(case_id)
        if case is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=404)
        if acc.role != "security_audit" or acc.readonly:
            raise AdminError(FORBIDDEN, MSG[FORBIDDEN], http_status=403)
        case.closed_at = self._now()
        case.review = review
        return case

    def _open_break_glass(self, acc: AdminAccount, reason: str) -> dict[str, Any]:
        case = BreakGlassCase(
            case_id=str(uuid.uuid4()),
            actor_id=acc.admin_id,
            reason=reason,
            alerted=True,
            opened_at=self._now(),
        )
        self.break_glass[case.case_id] = case
        msg = f"break-glass opened by {acc.login}"
        self.alerts.append(msg)
        if self._alert is not None:
            self._alert(msg)
        return {"break_glass_id": case.case_id, "alerted": True}

    def cookie_header(self, token: str) -> str:
        return (
            f"{ADMIN_COOKIE}={token}; Path={ADMIN_COOKIE_PATH}; "
            "Secure; HttpOnly; SameSite=Strict; Max-Age=3600"
        )
