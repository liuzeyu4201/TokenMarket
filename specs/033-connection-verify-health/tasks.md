# Tasks: 连接验证、能力发现与健康状态

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `provider-connection/v1` 至 1.2.0 并更新 catalog

## Phase 2: Foundational

- [x] T002 Alembic `0015_connection_health.py`
- [x] T003 [P] VendorProbe 端口、Catalog 交集、健康状态机、探测调度预算

## Phase 3: US1 可区分验证

- [x] T004 [US1] 先写失败测试：六类结果；买家 403；诊断无明文
- [x] T005 [US1] verify HTTP + 内部 unwrap purpose=verify

## Phase 4: US2 能力快照

- [x] T006 [US2] 先写失败测试：目录外交集丢弃；版本递增
- [x] T007 [US2] 快照持久化与 GET capabilities

## Phase 5: US3 滞后与预算

- [x] T008 [US3] 先写失败测试：单次故障不 unhealthy；1000 tick ≤ 预算
- [x] T009 [US3] ProbeScheduler + 阈值

## Phase 6: US4 UI 与手动复验

- [x] T010 [US4] 连接页健康/快照/立即复验；无 secret

## Phase 7: Polish

- [x] T011 迁移 head 0015；覆盖率 ≥80%；evidence
