# Tasks: 单会话与认证安全加固

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/single-session-auth/v1/` 并更新 `shared/contracts/README.md` 与 `tests/workflow/test_contracts.py`

## Phase 2: Foundational

- [x] T002 Alembic `0009_session_generation.py`：`users.session_generation` + `auth_sessions.session_generation` + `client_hint`
- [x] T003 扩展 User / AuthSession 模型与 `insert_session` / 世代提升仓储

## Phase 3: US1 替换

- [x] T004 [US1] 先写测试：第二次登录后仅一代、旧 cookie 立即引导失败、代理 Key 数量不变
- [x] T005 [US1] 登录与资料补全签发会话时同一事务 +1 世代并写入会话行

## Phase 4: US2 退出

- [x] T006 [US2] 先写测试：当前退出与全部退出；全部退出后世代+1；审计含 request ID
- [x] T007 [US2] 实现 `POST /session-revocations` `{scope:all}`（CSRF）

## Phase 5: US3 安全页

- [x] T008 [US3] 先写测试：已登录摘要无 token；匿名 401
- [x] T009 [US3] `GET /security-summary` + 前端 `/account/security`

## Phase 6: US4 负向

- [x] T010 [US4] CSRF 缺失不改世代；重放旧 cookie；猜测 token；缓存不可用仍拒绝已撤销

## Phase 7: Polish

- [x] T011 迁移 head 断言更新；evidence
