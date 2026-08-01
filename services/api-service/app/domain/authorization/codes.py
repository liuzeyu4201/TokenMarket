"""Stable authorization business codes and HTTP mapping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthzCode(str, Enum):
    OK = "0"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    NO_ROUTE_CANDIDATE = "NO_ROUTE_CANDIDATE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ReasonCode(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    ROLE_DENIED = "ROLE_DENIED"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_DELETED = "ACCOUNT_DELETED"
    ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
    NOT_OWNER = "NOT_OWNER"
    RESOURCE_MISSING = "RESOURCE_MISSING"
    RESOURCE_SOFT_DELETED = "RESOURCE_SOFT_DELETED"
    SELF_ROUTE_EMPTY = "SELF_ROUTE_EMPTY"
    FACT_STORE_UNAVAILABLE = "FACT_STORE_UNAVAILABLE"
    AUDIT_PERSIST_FAILED = "AUDIT_PERSIST_FAILED"
    VALIDATION = "VALIDATION"


@dataclass(frozen=True)
class PublicOutcome:
    code: AuthzCode
    http_status: int
    message: str


_MESSAGES: dict[AuthzCode, str] = {
    AuthzCode.OK: "success",
    AuthzCode.UNAUTHENTICATED: "未登录或会话已失效",
    AuthzCode.FORBIDDEN_ROLE: "当前角色无权执行该操作",
    AuthzCode.ACCOUNT_UNAVAILABLE: "账户不可用",
    AuthzCode.RESOURCE_NOT_FOUND: "资源不存在",
    AuthzCode.NO_ROUTE_CANDIDATE: "无可用路由资源",
    AuthzCode.VALIDATION_ERROR: "请求参数不合法",
    AuthzCode.SERVICE_UNAVAILABLE: "服务暂时不可用，请稍后重试",
    AuthzCode.INTERNAL_ERROR: "内部错误",
}

# Internal reason -> public code (never leak not_owner vs missing).
REASON_TO_PUBLIC: dict[ReasonCode, AuthzCode] = {
    ReasonCode.UNAUTHENTICATED: AuthzCode.UNAUTHENTICATED,
    ReasonCode.ROLE_DENIED: AuthzCode.FORBIDDEN_ROLE,
    ReasonCode.ACCOUNT_SUSPENDED: AuthzCode.ACCOUNT_UNAVAILABLE,
    ReasonCode.ACCOUNT_DELETED: AuthzCode.ACCOUNT_UNAVAILABLE,
    ReasonCode.ACCOUNT_INACTIVE: AuthzCode.ACCOUNT_UNAVAILABLE,
    ReasonCode.NOT_OWNER: AuthzCode.RESOURCE_NOT_FOUND,
    ReasonCode.RESOURCE_MISSING: AuthzCode.RESOURCE_NOT_FOUND,
    ReasonCode.RESOURCE_SOFT_DELETED: AuthzCode.RESOURCE_NOT_FOUND,
    ReasonCode.SELF_ROUTE_EMPTY: AuthzCode.NO_ROUTE_CANDIDATE,
    ReasonCode.FACT_STORE_UNAVAILABLE: AuthzCode.SERVICE_UNAVAILABLE,
    ReasonCode.AUDIT_PERSIST_FAILED: AuthzCode.SERVICE_UNAVAILABLE,
    ReasonCode.VALIDATION: AuthzCode.VALIDATION_ERROR,
}

_HTTP: dict[AuthzCode, int] = {
    AuthzCode.OK: 200,
    AuthzCode.UNAUTHENTICATED: 401,
    AuthzCode.FORBIDDEN_ROLE: 403,
    AuthzCode.ACCOUNT_UNAVAILABLE: 403,
    AuthzCode.RESOURCE_NOT_FOUND: 404,
    AuthzCode.NO_ROUTE_CANDIDATE: 404,
    AuthzCode.VALIDATION_ERROR: 400,
    AuthzCode.SERVICE_UNAVAILABLE: 503,
    AuthzCode.INTERNAL_ERROR: 500,
}


def public_outcome(reason: ReasonCode) -> PublicOutcome:
    code = REASON_TO_PUBLIC[reason]
    return PublicOutcome(
        code=code,
        http_status=_HTTP[code],
        message=_MESSAGES[code],
    )


def http_status_for_code(code: AuthzCode | str) -> int:
    c = AuthzCode(code) if isinstance(code, str) else code
    return _HTTP[c]
