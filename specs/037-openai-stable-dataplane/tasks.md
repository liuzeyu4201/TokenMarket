# Tasks: OpenAI 稳定数据面全兼容

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 扩展 `native-passthrough/v1` 至 1.2.0（openai-stable 覆盖说明）

## Phase 2: Foundational

- [x] T002 目录生成测试辅助：实例化 path、亲和预置、mode 选择

## Phase 3: US1 推理透传

- [x] T003 [US1] 先写测试：全部 openai stable 记录合同表
- [x] T004 [US1] 夹具：未知 JSON/query 保留；错误形状不改写

## Phase 4: US2 资源生命周期

- [x] T005 [US2] 先写测试：stateful shared 拒绝；dedicated 文件创建-查询钉住

## Phase 5: US3 Realtime

- [x] T006 [US3] 先写测试：catalog websocket 入口被承认

## Phase 6: US4 拒绝面

- [x] T007 [US4] 先写测试：全部 control_plane 不转发；未登记 404；preview 无 opt-in 403

## Phase 7: Polish

- [x] T008 覆盖报告与 ≥80% 包覆盖；env 门禁 live smoke 跳过
