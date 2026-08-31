"""Ledger business codes."""

from __future__ import annotations


class LedgerError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 409) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


INSUFFICIENT_QUOTA = "INSUFFICIENT_QUOTA"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
NOT_FOUND = "NOT_FOUND"
IMMUTABLE_ENTRY = "IMMUTABLE_ENTRY"
UNBALANCED = "UNBALANCED"
ALREADY_TERMINAL = "ALREADY_TERMINAL"
VALIDATION = "VALIDATION"
UNRESOLVED_HELD = "UNRESOLVED_HELD"

MSG = {
    INSUFFICIENT_QUOTA: "测试额度不足",
    IDEMPOTENCY_CONFLICT: "幂等键参数不一致",
    NOT_FOUND: "预留不存在",
    IMMUTABLE_ENTRY: "已发布分录不可修改或删除",
    UNBALANCED: "结算分录不平衡",
    ALREADY_TERMINAL: "预留已终结",
    VALIDATION: "请求参数不合法",
    UNRESOLVED_HELD: "成本未确定，预留保持未决",
}
