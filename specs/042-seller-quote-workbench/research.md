# Phase 0 Research：供给工作台

## Decision 1：报价落在 API-service

**Decision**: 卖家 Cookie 会话与 Connection 同进程。校验规则与 SF27 相同（整数 bps、buyer≥seller）。Billing Registry 仍是结算锁的权威；工作台产出可被锁引用的 seq。

## Decision 2：容量与生命周期分开

**Decision**: 声明容量是工作台状态；暂停仍走 SF16 lifecycle。admits_new = 生命周期允许 ∧ 容量≠0。

## Decision 3：收益分区

**Decision**: settled 仅显式入账；无账本时 settled=0 且 `ledger_ready=false`，unresolved 单独列出。
