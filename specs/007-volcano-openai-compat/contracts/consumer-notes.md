# 调用方说明：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/consumer-notes/v1`  
**Owner**: proxy-gateway

本功能只交付同进程适配结果。下列规则由下游实现，本仓库用契约测试锁定**本层输出**。

## SF12 非流式聊天代理

- 负责公开路径、买家认证、卖家 Key 选择、HTTP 状态映射与 `X-Request-ID`。
- 必须把更紧的公开截止传入本层 `context`（本层缺省 60s）。
- 成功：把 Compatible Chat Result 的兼容 JSON **原样语义**写给买家（非管理 API 包络）。
- 零事件失败：按 `error_category` 映射公开错误；永久类仅 `invalid`/`forbidden` 可驱动 Key 健康无效。

## SF15 流式聊天代理

- 将本层 `delta`/`done`/`truncated` 转为买家 SSE。
- 本层 `kind=error`（零事件）→ 公开 **尚未写 SSE 头** 时用统一错误结构。
- 本层已 yield `delta` 后 → 不得再写非流 JSON 错误体；截断只能结束流 + 日志。
- 不得依赖本层补造 `[DONE]` 来表示截断。

## SF16 健康

- 可将 `invalid`/`forbidden` 视为永久凭证问题。
- `rate_limited`/`timeout`/`temporary_unavailable`/`truncated_stream`/`invalid_response`
  **不得**覆盖为永久 invalid（与 SF06 合并纪律一致）。

## SF17 用量

- 只在本层 `error_category=success` 或流 `kind=done` 时消费 Usage Observation。
- `status=missing|inconsistent` 时不得把 0 当官方用量；估算属 SF17 自己的版本化规则。

## 非目标

- 本功能不实现公开 Handler、不选择 Key、不写账本、不调度健康探活。
