# Data Model：运行快照

## RuntimeSnapshot

| 字段 | 约束 |
|------|------|
| snapshot_id | 非空，单调或随机唯一 |
| catalog_major | 与 SF01 一致 |
| catalog | 只读 Endpoint Catalog 快照 |
| generation | uint64 递增 |

加载后不可变。

## SnapshotPin

持有 `*RuntimeSnapshot`；Unpin 只用于对称 API，不释放共享结构。

## DrainState

`serving` → `draining` → `stopped`。不可从 stopped 自动回到 serving（需新进程或显式 Resume 测试钩子）。
