# Runbook：火山方舟 Chat Completions 适配（SF07）

**Owner**: proxy-gateway  
**Signals**: `provider_chat_total{error_category}`、`provider_chat_truncated_total`、`provider_chat_duration_seconds`

## invalid_response

上游 HTTP 成功或 4xx 但无法得到可读 `choices`。优先怀疑官方契约变化（字段改名/类型）。对照 `shared/contracts/volcano-openai-compat/v1/upstream-volcano-chat.md` 复核文档后再改解析。

**不要**把该类写成卖家 Key 永久 invalid。

## truncated_stream

已向调用方交出至少一条兼容事件后连接断开/超时。多为网络或上游取消。查 `request_id` 与 duration。禁止补造 `[DONE]`。不得将截断当作永久 invalid。

## 限流

`rate_limited` + `retry_after_seconds`。本层不重试生成请求；由 SF12/SF14 决定冷却。

## 系统错误率告警（SF19）

规则：`ops/alerts/proxy.yml` 的 `TokenMarketProxySystemErrorRateHigh`。

- 分子：`proxy_requests_total{result=~"system_error|no_capacity"}`（5xx/上游失败/无可用 Key）
- 分母：全部合格代理请求
- **不**把 `auth_error` / `client_error`（无效代理 Key、参数 4xx）计入 5% 告警分子
- 触发：5 分钟窗口比率 >5% 且样本 ≥20，持续 5 分钟 → WARN/P1
- 恢复：比率 <3% 且样本 ≥20，**two consecutive** 评估窗口（再持续 5 分钟）后视为 resolved
- 看板：`infra/grafana/provisioning/dashboards/v01-proxy-overview.json`（刷新 10s；缺采集显示 No data，不得当 0）
