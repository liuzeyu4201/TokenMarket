# 错误分类契约：volcano-key-validation v1

**Contract ID**: `volcano-key-validation/error-classification/v1`  
**Owner**: proxy-gateway  
**Consumers**: SF08 seller key onboarding、SF16 health（及网关内调用方）

## 稳定枚举

| error_category | 含义 | 调用方是否可标永久 invalid | 建议动作 |
|----------------|------|---------------------------|----------|
| `success` | 认证有效、额度可信且 >0、至少一模型 | 否 | 可接入/可路由 |
| `invalid` | 认证失败 | **是** | `fix_credential` |
| `forbidden` | 权限不足 | **是** | `fix_credential` |
| `zero_quota` | 官方明确剩余为 0 | 否 | `add_quota` |
| `quota_unavailable` | 无可信额度读路径或字段不可用 | 否 | `retry_later` 或产品策略 |
| `no_supported_models` | 有效但无 V0.1 模型交集 | 否 | `enable_models` |
| `rate_limited` | 上游限流 | 否 | `retry_later`（读 `retry_after_seconds`） |
| `temporary_unavailable` | 暂时故障/并发闸门 | 否 | `retry_later` |
| `timeout` | 截止或上游超时 | 否 | `retry_later` |
| `invalid_response` | 协议/字段不符 | 否 | 告警；勿入路由池 |
| `unsupported_platform` | 非 volcano（V0.1） | 否 | `unsupported` |

**传输**：请求体 `platform` 为任意非空字符串；未知平台 **不得** 在 OpenAPI/JSON schema
层以 422 拒绝，MUST 返回业务完成响应（内部 HTTP：**200** + 本枚举）。

## HTTP 上游 → 分类（实现默认表）

| 上游 HTTP | 默认 error_category |
|-----------|---------------------|
| 401 | `invalid` |
| 403 | `forbidden` |
| 429 | `rate_limited` |
| 408 / client timeout | `timeout` |
| 5xx | `temporary_unavailable` |
| 网络拨号/连接错误 | `temporary_unavailable` |
| 200 + JSON 契约失败 | `invalid_response` |
| 200 + 无额度源 | 先完成模型步骤后 → `quota_unavailable`（V0.1 默认） |

不得依赖 `message` 中文/英文原文做主分类；仅可在契约测试金标中作辅助断言。

## 合并规则（调用方 MUST）

见 [consumer-merge-rules.md](./consumer-merge-rules.md)。
