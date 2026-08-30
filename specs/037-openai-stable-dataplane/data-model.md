# Data Model：OpenAI 稳定覆盖

沿用 EndpointRecord 与 AffinityBinding。本 SF 不新增持久化实体。

覆盖计数：

| 集合 | 定义 |
|------|------|
| stable | provider=openai 且 stability=stable |
| control_plane | provider=openai 且 stability=control_plane |
| preview | provider=openai 且 stability 为 preview 或 beta |
