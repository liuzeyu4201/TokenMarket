# Phase 0 Research

## Decision 1：30 天滚动错误预算

数据面目标 99.9%（月错误预算 0.1%），管理面 99.5%（0.5%）。剩余预算 / 总预算 < 0.20 则 freeze_release。

## Decision 2：标签允许列表

protocol、endpoint、status、plane、stream、result、reason、state。拒绝 user_id、project_id、request_id 及超过系列上限的组合。

## Decision 3：异步 link

usage 与 ledger hops 的 kind=link，request_id 与同步 span 相同，不另造根 trace。
