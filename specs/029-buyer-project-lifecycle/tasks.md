# Tasks: 买家 Project 生命周期与模式

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `shared/contracts/project/v1/project.openapi.yaml` 至 1.1.0 并更新 catalog 版本
- [x] T002 [P] 在 `shared/contracts/role-access-isolation/v1/` 增加 `project.*` 动作（expand-only）

## Phase 2: Foundational

- [x] T003 Alembic `services/api-service/alembic/versions/0011_buyer_projects.py`：表、部分唯一、mode 触发器、回退
- [x] T004 [P] `app/domain/projects/` 模型、状态机、Binding 端口、准入函数
- [x] T005 矩阵 `project.create|read|update|archive|delete|enable_protocol` 仅 buyer/both
- [x] T006 Actor.workspace；CORS PATCH；挂载路由与 `ProjectService`

## Phase 3: US1 创建与不可变 mode

- [x] T007 [US1] 先写失败测试：shared/dedicated 创建、PATCH mode 拒绝、同名冲突、并发同名
- [x] T008 [US1] 实现 `POST /api/v1/projects` 与 `PATCH`（无 mode）及幂等

## Phase 4: US2 状态机与归档准入

- [x] T009 [US2] 先写失败测试：合法转换、非法 409 行不变、归档后 ≤1s 准入 False
- [x] T010 [US2] 实现 activate/suspend/archive 与 `GET .../admission`

## Phase 5: US3 协议启用与删除阻塞

- [x] T011 [US3] 先写失败测试：无 Binding 启用 409；有 blocker 删除列出 kind；清空后逻辑删除再 GET 同形 404
- [x] T012 [US3] 实现 enable/disable 与 DELETE + 阻塞表读取

## Phase 6: US4 列表、IDOR、买家 UI

- [x] T013 [US4] 先写失败测试：他账号与未知 ID 同形 404；卖家工作区 403；CSRF
- [x] T014 [US4] HTTP 列表/详情隔离；前端 `/projects` 与详情页（模式后果、标签）
- [x] T015 [US4] Dashboard/壳层买家入口；卖家工作区无创建提交

## Phase 7: Polish

- [x] T016 迁移 head 断言 0011；领域包覆盖率 ≥80%；evidence

## Dependencies

Setup → Foundational → US1 → US2 / US3（可并行于领域层）→ US4 UI → Polish

## Independent tests

- US1: 创建两种 mode；改 mode 次数=0
- US2: 非法转换失败；归档准入立即 False
- US3: 启用协议成功次数=0（无 Binding）；删除含 blockers
- US4: 跨账号 GET 与未知 ID 的 code 一致；卖家 403

## MVP

T001–T008（可创建且 mode 不可变）即可演示；本功能需 US1–US4 全部完成才收敛。
