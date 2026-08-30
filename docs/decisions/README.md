**中文** | [English](README.en.md)

# 架构决策记录（ADR）

本目录记录 monorepo 的重大架构决策。每条 ADR 沿用 `001-github-actions-ci-adapter.md` 的结构：

- 背景与问题
- 决策所有者与相关方
- 备选方案
- 决策与后果
- 失败模式、运维成本、回滚路径
- 保留的替代方案

历史 ADR 正文保持撰写时的语言（多为英文或已中文化的 004），**不在此轮整篇翻译**。

## 索引

| ADR | 标题 | 状态 |
|-----|------|------|
| [001](001-github-actions-ci-adapter.md) | GitHub Actions 作为 `make ci` 的只读薄适配层 | Accepted |
| [002](002-local-compose-lifecycle.md) | 本地依赖生命周期走 Docker Compose | Accepted（实现已 Verified） |
| [003](003-layered-compose-deploy.md) | 分层 Compose 与 deploy 入口隔离 | Accepted |
| [004](004-hosted-toolchain-execution-profiles.md) | 托管工具链执行 profile | Accepted |
| [005](005-endpoint-catalog-governance.md) | V0.2 Endpoint Catalog 作为数据面范围唯一事实源 | Accepted |

## 何时写 ADR

在引入以下任一对象的 PR 中同时写入或更新 ADR：

- 新服务或组件
- 新存储或持久化模型
- 新协议或外部集成契约
- 被多个组件消费的新共享抽象
- 新的跨服务依赖

## 评审规则

1. ADR 与实现它的 PR 一起评审。
2. 相关组件 README 与可追溯清单必须链接该 ADR。
3. 合入后 ADR 不可改写历史；用新 ADR 取代，而不是改旧文。
