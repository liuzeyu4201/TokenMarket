"""Stable Project business codes."""

from __future__ import annotations

VALIDATION = "VALIDATION"
NAME_CONFLICT = "NAME_CONFLICT"
MODE_IMMUTABLE = "MODE_IMMUTABLE"
ILLEGAL_STATE_TRANSITION = "ILLEGAL_STATE_TRANSITION"
PROVIDER_BINDING_REQUIRED = "PROVIDER_BINDING_REQUIRED"
DELETE_BLOCKED = "DELETE_BLOCKED"
NOT_FOUND = "NOT_FOUND"
FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"

MSG = {
    VALIDATION: "请求参数不合法",
    NAME_CONFLICT: "同一账号下已存在相同名称的 Project",
    MODE_IMMUTABLE: "Project 模式创建后不可修改",
    ILLEGAL_STATE_TRANSITION: "非法状态转换",
    PROVIDER_BINDING_REQUIRED: "启用协议前必须存在对应 Provider Binding",
    DELETE_BLOCKED: "存在未清理的依赖，无法删除",
    NOT_FOUND: "资源不存在",
    FORBIDDEN_ROLE: "当前工作区无权执行该操作",
    IDEMPOTENCY_CONFLICT: "幂等键与请求内容不一致",
}

PROTOCOLS = frozenset({"openai", "anthropic", "vertex"})
MODES = frozenset({"shared", "dedicated"})
STATUSES = frozenset({"draft", "active", "suspended", "archived"})
BLOCKER_KINDS = frozenset({"key", "in_flight_task", "unsettled_ledger"})
