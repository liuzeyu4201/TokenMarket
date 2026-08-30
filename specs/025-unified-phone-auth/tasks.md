# Tasks: 统一手机号验证注册登录

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/unified-phone-auth/v1/` 并更新 `shared/contracts/README.md` 与 `tests/workflow/test_contracts.py`

## Phase 2: Foundational

- [x] T002 Alembic `services/api-service/alembic/versions/0008_unified_phone_auth.py`：挑战可空 `phone_normalized` + `profile_completion_intents`
- [x] T003 扩展 `VerificationChallenge` 模型与 `insert_pending_challenge`

## Phase 3: US1 中性发送

- [x] T004 [US1] 先写未知号码与已注册号码 challenge 公开形状一致测试（扩展既有反枚举）
- [x] T005 [US1] 未知号码挑战写入 `phone_normalized`；decoy 不写；dispatcher 对注册挑战投递

## Phase 4: US2 登录

- [x] T006 [US2] 既有 happy-path 登录测试仍通过（active 用户 OTP → 会话）

## Phase 5: US3 补全

- [x] T007 [US3] 先写单元/集成：OTP 后无用户行；补全后一行+会话；中断无半账号；50 并发一账号
- [x] T008 [US3] 实现 session_service 注册 OTP 分支与 `profile_completions` HTTP
- [x] T009 [US3] `POST /register` 无 cookie → `AUTH_VERIFICATION_REQUIRED`；有 cookie 可完成补全或一律走新路径

## Phase 6: US4 安全

- [x] T010 [US4] 负向：过期/重放 OTP、补全 cookie 过期、日志无 OTP
- [x] T011 [US4] 前端统一入口：Login 支持补全步骤；Register 走同一验证流；首页文案不再写「注册不自动登录」

## Phase 7: Polish

- [x] T012 迁移前后兼容测试；更新 Register 前端测试；evidence
