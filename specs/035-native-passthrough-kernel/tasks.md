# Tasks: 原生同协议透明代理核心

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 新增 `shared/contracts/native-passthrough/v1/` 并更新 catalog

## Phase 2: Foundational

- [x] T002 [P] 协议解析、目录准入、header 政策
- [x] T003 Selector 端口（Static / FailClosed）

## Phase 3: US1 透传

- [x] T004 [US1] 先写 golden：三协议未知字段与 query 不被删除
- [x] T005 [US1] ReverseProxy 内核 + `/openai|/anthropic|/vertex` 挂载

## Phase 4: US2 错误分层

- [x] T006 [US2] 先写失败测试：上游 429 原样；控制面平台信封
- [x] T007 [US2] ErrorHandler 仅用于传输失败

## Phase 5: US3 取消与上限

- [x] T008 [US3] 先写失败测试：取消 ≤1s；超大 body 不转发
- [x] T009 [US3] context 取消与 MaxBytesReader

## Phase 6: US4 无转换

- [x] T010 [US4] 源码扫描 passthrough 不引用 chatcompat

## Phase 7: Polish

- [x] T011 领域覆盖率 ≥80%；evidence
