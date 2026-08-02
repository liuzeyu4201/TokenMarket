# Runbook：火山方舟凭证验证（SF06）

## 症状

| 现象 | 可能原因 | 动作 |
|------|----------|------|
| 接入侧始终 `quota_unavailable` | V0.1 默认无 Key 额度 API（预期） | 确认是否已启用真实 `QuotaReader`；勿把结果当 `zero_quota` |
| 大量 `invalid` | 卖家 Key 错误/吊销 | 提示修正凭证；可写永久 invalid |
| 大量 `rate_limited` | 上游限流或并发过高 | 读 `retry_after_seconds`；检查全局 32 / 单 Key 1 闸门 |
| `invalid_response` | 上游契约变更 | 告警；更新 `upstream-volcano-models` 金标；阻止入池 |
| 内部路由 404 | flag 未开 | 仅在需要跨服务时开 `PROVIDER_VALIDATE_INTERNAL_ENABLED` |
| 启动失败 C1 | 非 local 启用且 bind 非回环 | 改 `PROVIDER_VALIDATE_BIND=127.0.0.1` 或私网 + `ALLOW_NON_LOOPBACK`（有期限） |

## 安全

- **禁止**仅靠 `X-Internal-Token` 将 `/internal/v1/provider-credentials/validate` 暴露在公网。
- test/prod 默认关闭内部路由；启用须网络隔离或 mTLS/服务身份。
- 日志/指标仅 `credential_ref`，禁止原始 Key。

## 回滚

1. `PROVIDER_VALIDATE_INTERNAL_ENABLED=false`
2. 回退 gateway 镜像
3. SF08/SF16 停止调用验证或降级

## 负责人

Proxy Gateway 维护者；接入/健康消费方见 SF08 / SF16。
