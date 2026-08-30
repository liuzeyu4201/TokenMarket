# Tasks: 厂商原生花费与多维用量采集

**Tests**: 先测试后实现。

- [x] T001 扩展 `usage/v1` 至 1.1.0
- [x] T002 [P] 先写解析夹具：三厂商 JSON；缺失不为 0；负数/溢出 unresolved
- [x] T003 [P] 实现 usageparse（openai/anthropic/vertex + digest）
- [x] T004 先写 SSE 合并与提前断开测试
- [x] T005 SSE 扫描实现
- [x] T006 目录计量策略矩阵（stable 全覆盖）
- [x] T007 内核挂钩：2xx 响应采集；事件无 raw_body
- [x] T008 Billing 观察信封校验；覆盖率 ≥80%；evidence
