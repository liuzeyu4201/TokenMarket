# Phase 0 Research：原生花费与用量

## Decision 1：扩展 usage/v1 1.1.0

**Decision**: 增加 parser_version、evidence_digest、settlement_basis、usage 维度、unresolved_reason。未知金额保持 null。

## Decision 2：解析器在网关

**Decision**: 数据面持有响应字节。Billing 只校验标准化观察。禁止 chatcompat 转换。

## Decision 3：货币微单位

**Decision**: `reported_cost_minor_units` 为币种 10^-6 整数（scale=6），用十进制字符串换算，不用 float64 乘算入账。

## Decision 4：SSE 合并后写

**Decision**: 按事件扫描 `usage` / `usageMetadata`，后帧覆盖同名字段；不缓存完整对话文本。
