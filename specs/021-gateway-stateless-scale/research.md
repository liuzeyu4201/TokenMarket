# Phase 0 Research：网关无状态化

## Decision 1：atomic.Value 快照 Holder + 请求 Pin

**Decision**: `Holder` 保存不可变 `Snapshot`。`Pin()` 返回当前指针；切换只替换 Holder 中的指针。请求全程使用 Pin 结果。

**Rationale**: 无锁读、无部分字段更新。

**Alternatives**: 互斥锁拷贝整个配置 — 更慢且易漏字段。

## Decision 2：本地 WAL 不是账务事实源

**Decision**: `DurableSink` 在 Dir 为空时只转发 Next。启动不得 Replay 本地文件作为入账前提。若设置 Dir，文件仅为可丢弃缓存，删除后仍启动。

**Rationale**: SF02 验收“无需恢复本地文件”。唯一持久化属 SF04 Outbox。

## Decision 3：Drain 用原子标志 + WaitGroup

**Decision**: `draining` 后新请求 503 `NOT_READY`；in-flight WaitGroup；超时取消。readiness 跟随 draining；liveness 不变。

**Rationale**: 滚动发布最小机制。
