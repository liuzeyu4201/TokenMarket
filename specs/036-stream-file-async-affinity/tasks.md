# Tasks: SSE、WebSocket、文件与异步资源亲和

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `native-passthrough/v1` 至 1.1.0

## Phase 2: Foundational

- [x] T002 [P] 亲和表 Put/Get/冲突；路径变量提取
- [x] T003 Selector.SelectConnection

## Phase 3: US1 SSE

- [x] T004 [US1] 先写测试：事件保序 flush；idle；取消
- [x] T005 [US1] SSE 流式转发与写超时

## Phase 4: US2 WebSocket

- [x] T006 [US2] 先写测试：Upgrade 转发；shared 拒绝 stateful WS
- [x] T007 [US2] websocket 端点保留 Upgrade

## Phase 5: US3 上传

- [x] T008 [US3] 先写测试：超限不转发；无 CreateTemp
- [x] T009 [US3] MaxBytesReader + 时长上限

## Phase 6: US4 亲和

- [x] T010 [US4] 先写测试：创建登记；后续钉住；缺失 fail-closed
- [x] T011 [US4] 响应 id 提取与 Get pin

## Phase 7: Polish

- [x] T012 短时并发 soak 夹具；覆盖率 ≥80%；evidence
