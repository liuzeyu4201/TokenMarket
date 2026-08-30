# Operations backup

Backup, retention and restore procedures for persistent engineering data.

V0.2 PostgreSQL 恢复目标与非生产演练步骤见
[`postgres-restore.md`](./postgres-restore.md)（RPO ≤5 分钟，RTO ≤30 分钟）。
Redis 仅保存可重建热状态，不能替代账本恢复。
