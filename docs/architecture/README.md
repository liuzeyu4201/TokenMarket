**中文** | [English](README.en.md)

# 架构

TokenMarket 是契约优先的 monorepo：Go 网关吃代理流量，Python 服务拥有领域与持久化，React 前端拥有展示，`shared/contracts` 先于消费者版本化。

## 从哪里读

| 文档 | 内容 |
|------|------|
| [overview.md](overview.md) | V0.1 **现状**数据流（与代码一致，不含未落地的 Kafka 本地依赖） |
| [`项目开发/技术架构/`](../../项目开发/技术架构/README.md) | 现状宣讲 PDF（详细）与约 2 小时 PPT |
| [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md) | 目标架构、服务职责、目录约定（含后续版本能力） |
| [`项目开发/2-Go代理网关开发规范.md`](../../项目开发/2-Go代理网关开发规范.md) | 网关实现约束 |
| [`项目开发/3-Python后端与数据库设计规范.md`](../../项目开发/3-Python后端与数据库设计规范.md) | FastAPI / PostgreSQL / 迁移 |
| [`项目开发/4-前端与DevOps监控规范.md`](../../项目开发/4-前端与DevOps监控规范.md) | 前端、CI、可观测 |
| [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) | 工程最高约束 |
| [ADR 索引](../decisions/README.md) | 已记录的架构决策 |

冲突时：**宪章 > 已接受的 ADR > 现行 `shared/contracts` > 架构规范原文中尚未落地的段落**。

## 组件 README

| 组件 | 说明 |
|------|------|
| [`services/proxy-gateway/README.md`](../../services/proxy-gateway/README.md) | 健康、内部凭证验证、公开 Chat Completions 代理 |
| [`services/api-service/README.md`](../../services/api-service/README.md) | 注册、会话、授权、卖家/代理 Key |
| [`services/billing-service/README.md`](../../services/billing-service/README.md) | 计费骨架与 PostgreSQL 就绪 |
| [`services/admin-service/README.md`](../../services/admin-service/README.md) | 管理骨架 |
| [`frontend/README.md`](../../frontend/README.md) | Web 前端 |
| [`shared/README.md`](../../shared/README.md) | 契约与校验工具 |
| [`infra/README.md`](../../infra/README.md) | Compose 与 Grafana 资产 |
| [`ops/README.md`](../../ops/README.md) | 运行手册与迁移所有权 |
