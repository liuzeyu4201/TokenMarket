"""High-risk wizards. Only confirmed runs execute(); cancel/timeout do not."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.domain.admin.errors import (
    MSG,
    VALIDATION,
    WIZARD_CANCELLED,
    WIZARD_EXPIRED,
    AdminError,
)
from app.domain.admin.service import AdminService

WIZARD_ACTION = {
    "replace_dedicated": "connection.replace_dedicated",
    "reverse": "ledger.reverse",
    "force_logout": "user.force_logout",
}

_IMPACT = {
    "replace_dedicated": [
        "专享绑定将切换连接",
        "无共享池回退",
        "进行中请求可能失败关闭",
    ],
    "reverse": [
        "账本追加冲正分录",
        "不修改历史余额字段",
        "必须填写财务原因",
    ],
    "force_logout": [
        "目标会话立即失效",
        "用户需重新登录",
    ],
}

TTL = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Wizard:
    wizard_id: str
    kind: str
    target: str
    impact: list[str]
    status: str
    request_id: str | None = None
    reason: str = ""
    created_at: datetime = field(default_factory=_now)
    expires_at: datetime = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "wizard_id": self.wizard_id,
            "kind": self.kind,
            "target": self.target,
            "impact": list(self.impact),
            "status": self.status,
            "request_id": self.request_id,
            "reason": self.reason,
            "expires_at": self.expires_at.isoformat(),
        }


class WizardService:
    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = TTL,
    ) -> None:
        self._now = now or _now
        self._ttl = ttl
        self._items: dict[str, Wizard] = {}

    def action_for(self, kind: str) -> str:
        action = WIZARD_ACTION.get(kind)
        if action is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        return action

    def start(self, *, kind: str, target: str, reason: str = "") -> Wizard:
        action = self.action_for(kind)
        _ = action
        item = Wizard(
            wizard_id=str(uuid.uuid4()),
            kind=kind,
            target=target,
            impact=list(_IMPACT[kind]),
            status="pending",
            reason=reason,
            created_at=self._now(),
            expires_at=self._now() + self._ttl,
        )
        self._items[item.wizard_id] = item
        return item

    def get(self, wizard_id: str) -> Wizard:
        item = self._items.get(wizard_id)
        if item is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=404)
        self._expire_if_due(item)
        return item

    def cancel(self, wizard_id: str) -> Wizard:
        item = self.get(wizard_id)
        if item.status == "confirmed":
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=409)
        item.status = "cancelled"
        return item

    def confirm(
        self,
        wizard_id: str,
        *,
        admin: AdminService,
        admin_token: str | None,
        user_cookie: str | None,
        request_id: str,
        reason: str,
    ) -> Wizard:
        item = self.get(wizard_id)
        if item.status == "cancelled":
            raise AdminError(WIZARD_CANCELLED, MSG[WIZARD_CANCELLED], http_status=409)
        if item.status == "expired":
            raise AdminError(WIZARD_EXPIRED, MSG[WIZARD_EXPIRED], http_status=409)
        if item.status != "pending":
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=409)
        admin.execute(
            admin_token=admin_token,
            user_cookie=user_cookie,
            action=self.action_for(item.kind),
            target=item.target,
            reason=reason or item.reason,
            request_id=request_id,
        )
        item.status = "confirmed"
        item.request_id = request_id
        return item

    def _expire_if_due(self, item: Wizard) -> None:
        if item.status != "pending":
            return
        if self._now() > item.expires_at:
            item.status = "expired"
