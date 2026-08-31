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
PATCH_ACTIVE_DENIED = "PATCH_ACTIVE_DENIED"
SIMULATE_FAILED = "SIMULATE_FAILED"
SIMULATE_REQUIRED = "SIMULATE_REQUIRED"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
WIZARD_CANCELLED = "WIZARD_CANCELLED"
WIZARD_EXPIRED = "WIZARD_EXPIRED"
SQL_EDITOR_DENIED = "SQL_EDITOR_DENIED"
NOT_FOUND = "NOT_FOUND"

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
    PATCH_ACTIVE_DENIED: "禁止直接修改已发布配置",
    SIMULATE_FAILED: "仿真失败，未改变线上版本",
    SIMULATE_REQUIRED: "发布前必须仿真通过",
    APPROVAL_REQUIRED: "发布前必须审批",
    WIZARD_CANCELLED: "向导已取消",
    WIZARD_EXPIRED: "向导已超时",
    SQL_EDITOR_DENIED: "后台不是数据库编辑器",
    NOT_FOUND: "对象不存在",
}

USER_COOKIE = "__Host-tokenmarket_session"
ADMIN_COOKIE = "__Host-tokenmarket_admin_session"
ADMIN_COOKIE_PATH = "/admin"
