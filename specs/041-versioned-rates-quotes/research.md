# Phase 0 Research：版本化费率

## Decision 1：bps 与微单位

**Decision**: 倍率万分比；金额 scale=6 微单位。`debit = (base * bps + 5000) // 10000` 半入。buyer_bps ≥ seller_max_bps 保证 spread≥0。

## Decision 2：状态机

**Decision**: draft → preview（校验）→ approved → published。新 publish 将旧 published 标 superseded，不删除。

## Decision 3：Gateway 只锁快照

**Decision**: 网关持有当前 published 快照；按 request_id 复制。报价计算在 Billing 用锁+capture 重放。
