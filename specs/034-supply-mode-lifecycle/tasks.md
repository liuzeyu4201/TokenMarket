# Tasks: 共享/专享供给模式与连接生命周期

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `provider-connection/v1` 至 1.3.0 并更新 catalog

## Phase 2: Foundational

- [x] T002 Alembic `0016_supply_lifecycle.py` 与专享 Binding 部分唯一索引
- [x] T003 [P] 状态机、阻塞端口、admits_new、池隔离查询

## Phase 3: US1 转换与模式锁定

- [x] T004 [US1] 先写失败测试：转换矩阵；listed 后改模式 409
- [x] T005 [US1] list/PATCH mode HTTP

## Phase 4: US2 暂停与阻塞

- [x] T006 [US2] 先写失败测试：pause ≤1s 阻止新路由；删除 blockers
- [x] T007 [US2] pause/drain/retire/delete

## Phase 5: US3 隔离

- [x] T008 [US3] 先写失败测试：共享池无 dedicated；专享 dual-bind 失败；retired 元数据可查
- [x] T009 [US3] routable 内部查询 + Binding unique

## Phase 6: US4 UI

- [x] T010 [US4] 连接页生命周期操作；上架后模式只读

## Phase 7: Polish

- [x] T011 迁移 head 0016；覆盖率 ≥80%；evidence
