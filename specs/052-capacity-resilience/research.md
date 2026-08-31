# Phase 0 Research

## Decision 1：内核内进程负载

对 `passthrough.Kernel.ServeHTTP` + `httptest` mock 加压，避免不可控网络；平台延迟 = 端到端 − mock 声明的 upstream 时延。

## Decision 2：Profile 常量不可缩小

稳态 500 RPS / 30m、突发 1000 RPS / 5m、流 500 / 2h 写死在契约与代码。测试传入显式 `Duration` 覆盖窗口，不得改 RPS/租户数。

## Decision 3：备份演练代码化

内存账本快照模拟 base backup；注入故障后 Restore 到空实例，断言 RPO/RTO。真实 PostgreSQL 物理演练仍以 `ops/backup/postgres-restore.md` 为准，未做生产实例演练则列为发布阻塞项。
