"""Budget admit codes."""

from __future__ import annotations


class BudgetError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 409) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


HARD_LIMIT = "HARD_LIMIT"
FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
NOT_FOUND = "NOT_FOUND"
VALIDATION = "VALIDATION"

MSG = {
    HARD_LIMIT: "已达测试额度硬上限，无法接受新预留",
    FORBIDDEN_ROLE: "当前工作区无权执行该操作",
    NOT_FOUND: "资源不存在",
    VALIDATION: "请求参数不合法",
}
