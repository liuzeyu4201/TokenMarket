# Phase 0 Research

## Decision 1：过滤在评分前独立包

**Decision**: `internal/domain/qualify` 不调用评分。QualifyingSelector 实现 passthrough.Selector。

## Decision 2：原因码稳定字符串

MODE, PROTOCOL, ENDPOINT, CAPABILITY, MODEL, REGION, HEALTH, CAPACITY, PRICE, LIFECYCLE, SELF_TRADE, DEDICATED
