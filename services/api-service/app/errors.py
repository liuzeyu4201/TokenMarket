"""Domain/transport errors that map to the unified business envelope."""

from __future__ import annotations

from typing import Any


class DependencyUnavailableError(Exception):
    """A required dependency is missing or down; respond with envelope 503."""

    def __init__(
        self,
        code: str = "SERVICE_UNAVAILABLE",
        message: str = "服务暂时不可用，请稍后重试",
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AuthBusinessError(Exception):
    """Authentication business failure with a stable public code.

    Codes follow ``shared/contracts/phone-auth-session/v1/business-codes.md``.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int,
        data: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data
        super().__init__(message)


# Stable message catalogue (clients must key off ``code``, not free text).
MSG_CHALLENGE_ACCEPTED = "若账户可用，验证码请求已受理"
MSG_PROFILE_COMPLETION_REQUIRED = "请补充昵称和角色以完成注册"
MSG_AUTH_VERIFICATION_REQUIRED = "请先完成手机号验证"
MSG_PROFILE_EXPIRED = "补全凭证无效或已过期，请重新获取验证码"
MSG_VALIDATION = "请求参数不合法"
MSG_ORIGIN_REJECTED = "来源不被允许"
MSG_CSRF_INVALID = "安全校验失败，请刷新后重试"
MSG_IDEMPOTENCY_REQUIRED = "缺少或无效的幂等键"
MSG_IDEMPOTENCY_CONFLICT = "幂等键与请求内容不一致"
MSG_IDEMPOTENCY_EXPIRED = "幂等键已过期，请使用新键重试"
MSG_RATE_LIMITED = "请求过于频繁，请稍后再试"
MSG_VERIFICATION_FAILED = "验证码错误或已失效"
MSG_CHALLENGE_UNAVAILABLE = "验证码不可用，请重新获取"
MSG_CHALLENGE_EXPIRED = "验证码已过期，请重新获取"
MSG_UNAUTHENTICATED = "未登录或会话已失效"
MSG_DELIVERY_UNAVAILABLE = "验证码服务暂时不可用，请稍后重试"
MSG_SERVICE_UNAVAILABLE = "服务暂时不可用，请稍后重试"
MSG_INTERNAL = "内部错误"
