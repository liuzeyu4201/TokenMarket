# Tasks: 代理网关无状态化与水平扩展

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 确认规格产物并新增 `ops/runbooks/gateway-stateless.md`

## Phase 2: Foundational

- [x] T002 [P] 创建 `services/proxy-gateway/internal/domain/runtimesnap/` 包骨架

## Phase 3: US1 快照

- [x] T003 [US1] 先写 `snap_test.go`：并发 Pin 期间 Swap 不混用 generation
- [x] T004 [US1] 实现 `snap.go` Holder/Pin/Swap；坏目录拒绝 Swap

## Phase 4: US2 无本地事实

- [x] T005 [US2] 先写 `usageobs` 测试：无 Dir 启动不 Replay；删除文件后不阻止启动
- [x] T006 [US2] 调整 DurableSink/main：默认不把 WAL 当 SoR；inflight 不落盘

## Phase 5: US3 Drain

- [x] T007 [US3] 先写 Drain 测试：新请求 503、liveness 200、在途 WaitGroup
- [x] T008 [US3] 实现 httpserver Drain 与 readiness 耦合

## Phase 6: US4 一致与脱敏

- [x] T009 [US4] 两 Holder 相同 catalog Admit 一致测试
- [x] T010 [US4] 复用/补充脱敏测试，确保密钥不进快照日志字段

## Phase 7: Polish

- [x] T011 接入 `cmd/gateway/main.go` 快照加载；写 evidence
