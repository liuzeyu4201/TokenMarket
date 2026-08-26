**中文** | [English](README.en.md)

# 文档枢纽

本目录是仓库文档的**分类入口**，不是所有原文的存放处。产品调研、PRD、规格、契约、运行手册仍在各自权威路径；这里只做归类、双语入口与缺页补齐。

语言约定见下方 [语言](#语言)。

## 分类

| 类别 | 权威路径 | 本枢纽 | 语言 |
|------|----------|--------|------|
| 仓库入口 | [`README.md`](../README.md) | — | 中文 + [`README.en.md`](../README.en.md) |
| 本地快速开始 | [`QUICKSTART.md`](../QUICKSTART.md) | — | 中文 + [`QUICKSTART.en.md`](../QUICKSTART.en.md) |
| 贡献与分支 | [`CONTRIBUTING.md`](../CONTRIBUTING.md) | — | 中文 + [`CONTRIBUTING.en.md`](../CONTRIBUTING.en.md) |
| 安全披露 | [`SECURITY.md`](../SECURITY.md) | — | 中英合订（GitHub 固定文件名） |
| 许可 | [`LICENSE`](../LICENSE) | — | 中英合订 |
| 架构 | [`项目开发/1-项目架构与目录结构.md`](../项目开发/1-项目架构与目录结构.md) | [`architecture/`](architecture/README.md) | 枢纽双语；规范原文中文 |
| HTTP / 事件契约 | [`shared/contracts/`](../shared/contracts/README.md) | [`api/`](api/README.md) | 契约英文标识；说明双语 |
| 产品与调研 | [`产品调研/`](../产品调研/README.md)、[`项目开发/`](../项目开发/README.md) | [`product/`](product/README.md) | 原文中文；枢纽双语 |
| 架构决策 | [`docs/decisions/`](decisions/README.md) | 本目录 | 索引双语；历史 ADR 保持原文 |
| 功能规格 | [`specs/`](../specs/)、[`项目开发/V0.1/V0.1_0712/specs/`](../项目开发/V0.1/V0.1_0712/specs/README.md) | [`product/`](product/README.md) | 中文 |
| 运行手册 | [`ops/runbooks/`](../ops/runbooks/README.md) | — | 中文 |
| 工程宪章 | [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) | — | 英文（历史权威，不在此轮整篇翻译） |

## 按读者

| 你想… | 打开 |
|--------|------|
| 跑起本地环境 | [`QUICKSTART.md`](../QUICKSTART.md) |
| 理解服务边界 | [`architecture/README.md`](architecture/README.md) |
| 查某个 HTTP 接口 | [`api/README.md`](api/README.md) → `shared/contracts/` |
| 读 PRD / 路线图 / 调研 | [`product/README.md`](product/README.md) |
| 查为什么这样设计 | [`decisions/README.md`](decisions/README.md) |
| 排障、迁移、部署 | [`ops/runbooks/README.md`](../ops/runbooks/README.md) |
| 实现某个 V0.1 功能 | [`specs/`](../specs/) 对应 `NNN-…` 目录 |

## 语言

| 文档类型 | 规则 |
|----------|------|
| 仓库入口、快速开始、贡献指南、本枢纽 | 简体中文为默认文件名；英文对照为同名 `*.en.md` |
| 新写或大幅修订的工程说明 | 简体中文（宪章原则 VIII） |
| 代码标识、API 字段、命令、路径、环境变量 | 保持原文，不翻译 |
| OpenAPI / JSON Schema / 工作流契约 | 英文标识；说明文字可中文 |
| 已存在的英文 ADR、宪章、组件 README | 保持原文，不整篇回译；新段落用中文或提供 `*.en.md` 索引 |

不要把 `产品调研/`、`项目开发/`、`specs/`、`shared/contracts/` 搬进 `docs/`。搬迁会切断规格、测试与宪章中的权威路径。

## 本目录树

```text
docs/
├── README.md / README.en.md     # 本枢纽
├── architecture/                # 架构索引与 V0.1 现状图
├── api/                         # 对外接口导航 → shared/contracts
├── product/                     # 产品 / 调研 / 规格导航
└── decisions/                   # ADR（路径由测试固定）
```
