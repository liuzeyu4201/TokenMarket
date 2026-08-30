# Phase 0 Research：OpenAI 稳定数据面

## Decision 1：覆盖率分母 = 嵌入目录

**Decision**: `LoadEmbedded(1)` 过滤 `provider=openai && stability=stable`。测试表由目录生成，禁止维护第二份路径列表。

## Decision 2：路径实例化

**Decision**: `{var}` 替换为 `tm-{var}`；`affinity=resource_id` 且路径含资源 ID 时先 Put 亲和，避免 GET/DELETE fail-closed。

## Decision 3：真实冒烟门禁

**Decision**: `TOKENMARKET_OPENAI_SMOKE=1` 才启用；默认 CI 只用 httptest 上游。不得把 mock 计入“真实冒烟通过”。
