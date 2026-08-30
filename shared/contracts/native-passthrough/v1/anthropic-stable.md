# Anthropic 稳定数据面：native-passthrough v1.3

**Owner**: Proxy Gateway

冻结日 Endpoint Catalog 中 `provider=anthropic` 且 `stability=stable` 的记录必须经同协议内核可达。

- 覆盖率分母等于上述记录数。
- 保留 `anthropic-version`、Anthropic 错误信封、request ID、rate-limit 头与 SSE 事件名；禁止改写成 OpenAI chunk。
- Files/Skills 等 beta 默认拒绝，需 Project opt-in。
- Message Batches 为 stateful，仅 dedicated 并按 resource_id 亲和。

`TOKENMARKET_ANTHROPIC_SMOKE` 显式启用真实冒烟；不得替代目录合同测试。
