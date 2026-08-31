# Phase 0 Research

## Decision 1：证据事件幂等

`event_id` 唯一。乱序时 reported 覆盖结算口径；若已 usage 结算则 `apply_delta` 追加，不改原分录。

## Decision 2：未决 case 与 reservation 分离

reservation 保持 held/unresolved；case 记录 reason/SLA/owner。恢复时允许从 unresolved 走 settle，使用原 `rate_version`。

## Decision 3：差异工单

`|reported_buyer - computed_buyer| > threshold` 生成 VARIANCE 工单，不下调原金额为 0。
