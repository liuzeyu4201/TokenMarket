# Feature Specification: 高可用部署、滚动发布与回滚

**Feature Branch**: `024-ha-deploy-rollout-rollback`
**Created**: 2026-08-31
**Status**: Implemented
**Source Feature**: SF05

## Clarifications

- 环境仅显式 `mode=test|prod`，不从 Git 分支推断。
- 回滚不得删除账本/用量卷。
- 完整 500 RPS 滚动曲线属 SF33；本 SF 冻结拓扑、健康检查、摘流宽限、备份恢复手册与自动化结构检查。

## User Stories

### US1 可复现部署资产 (P1)
分层 Compose 无 `build:`，镜像注入，健康检查与 stop_grace 支持摘流。

### US2 回滚不毁数据 (P1)
deploy-down 与回滚手册禁止 `--volumes`。

### US3 备份恢复目标 (P1)
手册声明 RPO ≤5 分钟、RTO ≤30 分钟，并给出非生产恢复步骤。

## Requirements

- **FR-001**: 应用 Compose MUST 使用 `image:` 且 MUST NOT 使用 `build:`。
- **FR-002**: 每个应用服务 MUST 有 healthcheck 与 stop_grace_period。
- **FR-003**: Gateway stop_grace_period MUST ≥ 30s。
- **FR-004**: deploy-down MUST NOT 删除 named volumes。
- **FR-005**: 运行手册 MUST 含滚动、停止条件、回滚、备份恢复。
- **FR-006**: 未提供 mode 或 prod 秘密时失败关闭（沿用既有门禁）。

## Success Criteria

- **SC-001**: 结构测试 100% 断言 FR-001–FR-004。
- **SC-002**: 手册含 RPO 5 分钟与 RTO 30 分钟。
