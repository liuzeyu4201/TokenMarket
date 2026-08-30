# Tasks: 多协议 Provider Binding

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/provider-binding/v1/` 并更新 catalog
- [x] T002 [P] 矩阵增加 `binding.*` 动作

## Phase 2: Foundational

- [x] T003 Alembic `0012_provider_bindings.py`：表、单 active 部分唯一、回退
- [x] T004 [P] `app/domain/bindings/` 模型、状态机、Connection/价格端口、SDK 提示
- [x] T005 挂载 HTTP、Actor 工作区、CSRF；ProjectService 注入真实 BindingLookup

## Phase 3: US1 三协议发布与 SDK 提示

- [x] T006 [US1] 先写失败测试：三协议同时 active；SDK 无 secret；卖家 403
- [x] T007 [US1] 实现创建/发布/sdk-hint

## Phase 4: US2 版本与并发

- [x] T008 [US2] 先写失败测试：并发发布仅一 active；旧 version 行不变；新请求 ≤1s 读新 version
- [x] T009 [US2] 实现校验/发布事务与不可变已发布行

## Phase 5: US3 模式、跨协议、降级

- [x] T010 [US3] 先写失败测试：mode 不一致拒绝；跨协议准入拒绝；degraded 无共享回退
- [x] T011 [US3] 实现 admit 与 degrade_for_connection

## Phase 6: US4 启用协议与 UI

- [x] T012 [US4] 先写失败测试：发布后启用协议成功；未发布仍 409
- [x] T013 [US4] Project 详情 Binding 表单与 SDK 提示（无凭据）

## Phase 7: Polish

- [x] T014 迁移 head 0012；覆盖率 ≥80%；evidence

## Independent tests

- US1: 三协议 SDK 提示互异且无 secret
- US2: 并发 active 行数 = 1
- US3: mode/跨协议/degraded 成功次数 = 0
- US4: 启用协议在发布前后结果不同
