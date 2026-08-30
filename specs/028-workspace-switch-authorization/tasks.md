# Tasks: 买家卖家工作区切换与路由授权

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/workspace-switch/v1/` 并更新 catalog

## Phase 2: Foundational

- [x] T002 Alembic `0010_session_workspace.py` 与 AuthSession.workspace
- [x] T003 登录签发默认工作区；bootstrap 返回 workspace

## Phase 3: US1 切换

- [x] T004 [US1] 先写切换成功/未授权 403/CSRF 测试
- [x] T005 [US1] `POST /api/v1/auth/workspace` + 前端 both 切换并清草稿

## Phase 4: US2 授权

- [x] T006 [US2] 先写 both+买家禁卖家动作、忽略客户端 workspace 测试
- [x] T007 [US2] AuthorizationService 按会话工作区求交

## Phase 5: US3 自排除

- [x] T008 [US3] 10 万次随机排除属性测试

## Phase 6: US4 导航

- [x] T009 [US4] 壳层工作区标识、buyer 不可切、无管理员入口

## Phase 7: Polish

- [x] T010 迁移 head 断言；evidence
