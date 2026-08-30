# OpenAI 稳定数据面：native-passthrough v1.2

**Owner**: Proxy Gateway

冻结日 Endpoint Catalog 中 `provider=openai` 且 `stability=stable` 的记录必须经同协议内核可达。

- 覆盖率分母等于上述记录数；禁止手写第二份路径白名单。
- 只替换平台代理鉴权；保留 OpenAI 请求 ID、错误 JSON、usage 与流事件形状。
- `control_plane` 不得透传。`preview`/`beta` 默认拒绝，Project opt-in 后才开放。
- stateful / `affinity=resource_id|connection` 仅 dedicated。

真实厂商冒烟不替代目录合同测试；由 `TOKENMARKET_OPENAI_SMOKE` 显式启用。
