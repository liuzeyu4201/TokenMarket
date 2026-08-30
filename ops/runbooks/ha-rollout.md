# 高可用滚动发布与回滚

Owner: 发布负责人 + 基础设施维护者

环境选择必须显式 `mode=test` 或 `mode=prod`，禁止从 Git 分支推断。

## 拓扑

数据面至少两个 Gateway 副本（滚动时先摘流再替换）。应用镜像来自 `make build` 的不可变 tag/digest。`infra/docker/compose.app.yml` 为 Layer A；不得把业务服务写入 `compose.local.yml`。

## 滚动步骤

1. `make build`
2. 确认候选镜像 digest 与 `make ci` 证据。
3. `make deploy mode=test`（生产再 `mode=prod` 且已审批）。
4. 逐副本：readiness 失败（Drain）→ 替换镜像 → live/ready 通过。
5. `make migrate mode=…` 仅在 expand 阶段；contract 阶段在旧读者下线后。

停止条件：错误率升高、账本对账失败、目录主版本不兼容。立即回滚镜像，不删卷。

## 回滚

1. 部署上一不可变镜像。
2. 禁止 `deploy-down --volumes` 或手动 `docker volume rm`。
3. schema 必须仍可被回滚后的应用读写（expand/migrate/contract）。
4. 用量 outbox / 账本分录不得删除。

## 备份与恢复

见 `ops/backup/postgres-restore.md`。目标：RPO ≤ 5 分钟，RTO ≤ 30 分钟。Redis 只恢复可重建热状态，不以 Redis 备份充当账本。
