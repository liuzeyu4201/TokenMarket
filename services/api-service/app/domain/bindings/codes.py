"""Stable Binding business codes."""

from __future__ import annotations

VALIDATION = "VALIDATION"
NOT_FOUND = "NOT_FOUND"
FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
MODE_MISMATCH = "MODE_MISMATCH"
CONNECTION_REQUIRED = "CONNECTION_REQUIRED"
PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"
MODEL_NOT_ALLOWED = "MODEL_NOT_ALLOWED"
BINDING_DEGRADED = "BINDING_DEGRADED"
BINDING_REQUIRED = "BINDING_REQUIRED"
PUBLISH_CONFLICT = "PUBLISH_CONFLICT"
ILLEGAL_STATE_TRANSITION = "ILLEGAL_STATE_TRANSITION"
IMMUTABLE_VERSION = "IMMUTABLE_VERSION"
BUYER_CONFIRMATION_REQUIRED = "BUYER_CONFIRMATION_REQUIRED"
STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
BINDING_REPLACE_DENIED = "BINDING_REPLACE_DENIED"

MSG = {
    VALIDATION: "请求参数不合法",
    NOT_FOUND: "资源不存在",
    FORBIDDEN_ROLE: "当前工作区无权执行该操作",
    MODE_MISMATCH: "Binding 供给方式必须与 Project 模式相同",
    CONNECTION_REQUIRED: "专享 Binding 必须指向可用的专享 Connection",
    PRICE_UNAVAILABLE: "所选协议缺少可用的稳定数据面/价格",
    PROTOCOL_MISMATCH: "禁止跨协议映射",
    MODEL_NOT_ALLOWED: "模型不在 Binding 允许列表中",
    BINDING_DEGRADED: "专享 Binding 已降级，不会回退共享池",
    BINDING_REQUIRED: "该协议没有生效的 Binding",
    PUBLISH_CONFLICT: "同一协议并发发布冲突，请重试",
    ILLEGAL_STATE_TRANSITION: "非法状态转换",
    IMMUTABLE_VERSION: "已发布的 Binding 版本不可修改",
    BUYER_CONFIRMATION_REQUIRED: "更换专享连接需要买家确认",
    STEP_UP_REQUIRED: "更换专享连接需要 step-up 校验",
    BINDING_REPLACE_DENIED: "仅专享 Binding 支持人工更换",
}

PROTOCOLS = frozenset({"openai", "anthropic", "vertex"})
MODES = frozenset({"shared", "dedicated"})
PUBLISHED = frozenset({"active", "inactive", "degraded"})

SDK_HINTS = {
    "openai": {
        "protocol": "openai",
        "base_url": "/v1",
        "auth_scheme": "bearer",
        "protocol_version": "v1",
    },
    "anthropic": {
        "protocol": "anthropic",
        "base_url": "/v1",
        "auth_scheme": "x-api-key",
        "protocol_version": "v1",
    },
    "vertex": {
        "protocol": "vertex",
        "base_url": "/v1",
        "auth_scheme": "bearer",
        "protocol_version": "v1",
    },
}
