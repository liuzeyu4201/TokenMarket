# Phase 0 Research：供给模式生命周期

## Decision 1：lifecycle_state 新列，不复用 status

**Decision**: `status` 仍表示凭据是否销毁（active|deleted）。`lifecycle_state` 为供给生命周期。

## Decision 2：上架锁定模式

**Decision**: PATCH supply_mode 仅 draft/verified。listed 起 MODE_LOCKED。切模式路径：pause/drain → 解绑 → 无阻塞 → verified → PATCH → list。

## Decision 3：shared 不进入 bound

**Decision**: bound 仅 dedicated + 活动 Binding。shared 保持 listed 直到 pause/drain/retire。

## Decision 4：admits_new

**Decision**: `usable` 且 lifecycle∈{listed,bound} 且 health=healthy 且 capability_version>0。pause/drain/retired 立即 false。HealthFact 增加 admits_new。

## Decision 5：阻塞端口

**Decision**: Binding 活动绑定、InFlightLookup、UnsettledLookup。后两者默认空，测试注入。
