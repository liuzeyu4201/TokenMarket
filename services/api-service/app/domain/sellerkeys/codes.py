"""Stable onboarding / lifecycle business codes."""

from __future__ import annotations


class OnboardingError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


CODE_UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
CODE_INVALID_KEY = "INVALID_KEY"
CODE_FORBIDDEN = "FORBIDDEN"
CODE_ZERO_QUOTA = "ZERO_QUOTA"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_TEMPORARY = "TEMPORARY_UNAVAILABLE"
CODE_DUPLICATE = "DUPLICATE_CREDENTIAL"
CODE_ENCRYPTION = "ENCRYPTION_FAILURE"
CODE_QUOTA_UNAVAILABLE = "QUOTA_UNAVAILABLE"
CODE_UNAUTHORIZED = "UNAUTHORIZED"
CODE_CONFLICT = "STATE_CONFLICT"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_VALIDATION_FAILED = "VALIDATION_FAILED"

MSG = {
    CODE_UNSUPPORTED_PLATFORM: "平台不受支持",
    CODE_INVALID_KEY: "凭证无效",
    CODE_FORBIDDEN: "凭证权限不足",
    CODE_ZERO_QUOTA: "额度不足，无法接入",
    CODE_RATE_LIMITED: "上游限流，请稍后重试",
    CODE_TEMPORARY: "暂时无法验证，请稍后重试",
    CODE_DUPLICATE: "该凭证无法接入",
    CODE_ENCRYPTION: "凭证保护失败，请稍后重试",
    CODE_QUOTA_UNAVAILABLE: "额度不可读，请稍后重试或联系支持",
    CODE_UNAUTHORIZED: "需要卖家身份",
    CODE_CONFLICT: "状态冲突",
    CODE_NOT_FOUND: "资源不存在",
    CODE_VALIDATION_FAILED: "重新验证未通过，Key 保持暂停",
}
