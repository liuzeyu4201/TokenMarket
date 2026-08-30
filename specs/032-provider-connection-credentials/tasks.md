# Tasks: Provider Connection 与凭据安全

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `shared/contracts/provider-connection/v1/` 至 1.1.0 并更新 catalog

## Phase 2: Foundational

- [x] T002 Alembic `0014_provider_connections.py`
- [x] T003 [P] SSRF 校验器（HTTPS、私网、metadata、redirect）
- [x] T004 矩阵 `connection.*` 仅 seller/both

## Phase 3: US1 创建无读回

- [x] T005 [US1] 先写失败测试：201 无 secret；GET 无明文；买家 403；库无明文
- [x] T006 [US1] 创建加密 + fingerprint + HTTP

## Phase 4: US2 unwrap 与轮换

- [x] T007 [US2] 先写失败测试：无令牌 unwrap 失败；previous key 可解
- [x] T008 [US2] 内部 unwrap + 审计无明文

## Phase 5: US3 SSRF、替换、删除

- [x] T009 [US3] 先写失败测试：SSRF 矩阵；并发替换无混搭；删除后 unwrap 失败
- [x] T010 [US3] 替换版本 CAS；删除 wipe；degrade Binding

## Phase 6: US4 UI

- [x] T011 [US4] 卖家 `/connections` 表单 password，创建后不回显；买家 forbidden

## Phase 7: Polish

- [x] T012 迁移 head 0014；覆盖率 ≥80%；evidence
