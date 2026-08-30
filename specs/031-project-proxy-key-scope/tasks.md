# Tasks: Project 代理 Key 与权限范围

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/project-proxy-key/v1/` 并更新 catalog
- [x] T002 网关 `defaultPosTTL` 改为 1s 并补测试

## Phase 2: Foundational

- [x] T003 Alembic `0013_project_proxy_key_scope.py` 扩展 proxy_keys 与配额表
- [x] T004 扩展 IssuedProxyKey / SQL 映射

## Phase 3: US1 签发

- [x] T005 [US1] 先写失败测试：归属 Project、Binding 子集、一次明文、列表无明文
- [x] T006 [US1] `POST /api/v1/projects/{id}/proxy-keys` + HMAC 存储

## Phase 4: US2 限制

- [x] T007 [US2] 先写失败测试：协议/模型/CIDR/过期/额度正负向与并发额度
- [x] T008 [US2] `authorize` 交集 + 原子配额 + compare_digest

## Phase 5: US3 轮换禁用撤销

- [x] T009 [US3] 先写失败测试：轮换旧 secret 失败；撤销 ≤1s；撤销不可启用
- [x] T010 [US3] rotate/disable/enable/revoke

## Phase 6: US4 UI 与 IDOR

- [x] T011 [US4] 先写失败测试：跨 Project 404；卖家 403
- [x] T012 [US4] 买家 UI 签发与掩码列表

## Phase 7: Polish

- [x] T013 迁移 head 0013；覆盖率 ≥80%；evidence

## Independent tests

- US1: 库中无完整 secret
- US2: 五项限制矩阵 + 并发额度
- US3: 撤销 1s
- US4: IDOR 同形
