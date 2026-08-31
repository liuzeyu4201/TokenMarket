"""Admin identity and audit codes."""

from __future__ import annotations


class AdminError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 403) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


UNAUTHORIZED = "UNAUTHORIZED"
USER_SESSION_REJECTED = "USER_SESSION_REJECTED"
FORBIDDEN = "FORBIDDEN"
STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
MFA_REQUIRED = "MFA_REQUIRED"
REASON_REQUIRED = "REASON_REQUIRED"
IMMUTABLE_AUDIT = "IMMUTABLE_AUDIT"
PROMOTION_DENIED = "PROMOTION_DENIED"
VALIDATION = "VALIDATION"

MSG = {
    UNAUTHORIZED: "需要管理员会话",
    USER_SESSION_REJECTED: "用户会话不能访问管理员入口",
    FORBIDDEN: "当前角色无权执行该操作",
    STEP_UP_REQUIRED: "高风险操作需要近期 step-up",
    MFA_REQUIRED: "高风险操作需要 MFA",
    REASON_REQUIRED: "高风险操作需要原因",
    IMMUTABLE_AUDIT: "审计记录不可修改或删除",
    PROMOTION_DENIED: "禁止将普通用户提升为管理员",
    VALIDATION: "请求参数不合法",
}

USER_COOKIE = "__Host-tokenmarket_session"
ADMIN_COOKIE = "__Host-tokenmarket_admin_session"
ADMIN_COOKIE_PATH = "/admin"
