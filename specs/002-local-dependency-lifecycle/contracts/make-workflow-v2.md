# 契约：Root Make Workflow v2 迁移

**版本**: 2.0.0
**所有者**: 仓库维护者
**取代**: 在激活门禁之后为 `shared/contracts/repository-workflow/v1/make-workflow.md`
**破坏原因**: `dev` 与 `dev-down` 由失败关闭（fail-closed）过渡目标变为成功的、会改变状态的本地生命周期目标

## 稳定表面

根 Makefile 仍是唯一公共入口。既有目标名称、mode 语法、`0 = success`、非零失败、脱敏、可访问文本、JSONL 可用性，以及全部非 SF02 目标行为保持不变。

| 目标 | v2 目的 | 副作用 | 成功证据 |
|--------|------------|--------------|------------------|
| `dev` | 状态协调 SF02 本地依赖 | 全部前置检查通过后，精确工作区的容器、网络与声明存储 | PostgreSQL、Redis 与 Grafana 各自在共享截止时间内产生即时认证就绪检查证据 |
| `dev-down` | 停止精确工作区的 SF02 环境 | 移除精确项目容器/孤儿与临时网络；保留 PostgreSQL/Redis 命名卷 | 不存在精确项目容器/网络；仅卷状态为 `already stopped` |

完整的配置、身份、顺序、健康、数据、诊断与恢复规则见 [`local-environment-lifecycle.md`](./local-environment-lifecycle.md)。JSONL 遵循 [`workflow-event-v2.0.schema.json`](./workflow-event-v2.0.schema.json) 中的标准事件封装；当前 workflow-step 字段位于其严格 payload 内，而非信封根部。

## 兼容性与迁移窗口

本变更有意不作为 v1 兼容发布：

1. **公告期**：落地本 v2 契约、event v2 schema、迁移通知与失败的消费者测试，同时可执行体仍返回 v1 `SF02_NOT_READY` 行为。`make help` 标明待定的 v2 激活，并链接恢复/数据效果。
2. **消费者迁移门禁**：更新每个仓库拥有的事件读取器、夹具、契约测试、文档引用与 CI 解析器以接受 v2。契约检查枚举这些消费者；未知或仍为 v1 的消费者阻止激活。
3. **激活**：仅在生命周期、隔离、持久化、脱敏、失败恢复与双平台验收证据通过后，实现才可将 `dev`/`dev-down` 切换为 v2 语义，并使 event v2 成为默认。
4. **弃用窗口**：在激活后至少到下一个 tagged 仓库发布前，保留不可变的 v1 Make/event 产物与迁移通知。在此窗口内不得新增针对 v1 的消费者。v1 仍为历史文档，而非 SF02 可选的成功模式，因其无法安全表达依赖状态。

不允许双重执行：单次调用不能既以 `SF02_NOT_READY` 失败又变更本地资源。不发出双重 JSONL 流，因为严格 v1 读取器拒绝依赖字段且无法表示 `WAITING`；消费者在激活前迁移。

## 回滚

经评审的回滚一并重新启用 v1 失败关闭实现与 v1 事件输出。它可以保留精确项目的 PostgreSQL/Redis 卷，但永不删除它们。重新启用 v2 需要再次通过完整激活门禁。
