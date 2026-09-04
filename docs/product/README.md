**中文** | [English](README.en.md)

# 产品、调研与规格

产品叙事与工程规格**不搬进 `docs/`**。本页把三类原文归到各自权威目录。

冲突时：**宪章 > V0.2 总纲与横切规则 > SF / Spec Kit 功能规格 > PRD > 架构/语言规范**。见 [`项目开发/V0.2/V0.2_0831/README.md`](../../项目开发/V0.2/V0.2_0831/README.md)。

## 产品定义（`项目开发/`）

完整索引：[`项目开发/README.md`](../../项目开发/README.md)

| 文档 | 用途 |
|------|------|
| [V0.2 实现文档索引](../../项目开发/V0.2/V0.2_0831/README.md) | V0.2 范围、优先级、已确认决策 |
| [V0.2 实现总纲](../../项目开发/V0.2/V0.2_0831/V0.2_0831_实现总纲.md) | 版本目标、用户旅程、成功标准 |
| [功能清单与依赖矩阵](../../项目开发/V0.2/V0.2_0831/功能清单与依赖矩阵.md) | SF01–SF34 与实施批次 |
| [产品需求文档（PRD）](../../项目开发/产品需求文档（PRD）.md) | 长期定位与价值（资金闭环段落以 V0.2 总纲为准） |
| [产品迭代路线图](../../项目开发/产品迭代路线图.md) | 多版本主题；与 V0.2 冲突的充值/提现不进入本版本 |
| [V0.1 子 Spec 索引](../../项目开发/V0.1/V0.1_0712/specs/README.md) | 历史 SF01–SF19 |
| [架构与目录](../../项目开发/1-项目架构与目录结构.md) | 目标架构 |

## 市场调研（`产品调研/`）

完整索引：[`产品调研/README.md`](../../产品调研/README.md)

| 目录 | 用途 |
|------|------|
| `商业计划书/` | 商业计划章节、合订、[宣传 PPT](../../产品调研/商业计划书/TokenMarket_宣传PPT.pptx) |
| `竞品分析/` | 网关、转售、国内市场、间接竞品 |
| `厂商调研/` | 模型与平台厂商 |
| `战略与生态规划/` | Coding Plan 生态与综合调研 |

## 实现规格（`specs/`）

Spec Kit 功能目录 `specs/NNN-short-kebab/` 与 Git 分支名一致。每个目录含 `spec.md`、`plan.md`、`tasks.md`、契约与证据。

V0.2 的 SF 与目录是一对一映射（编号不按 SF 序号连续，按依赖批次占用空号）：

| 批次 | SF → `specs/` |
|------|----------------|
| 工程基线 | SF01 `020-endpoint-catalog-governance` · SF02 `021-gateway-stateless-scale` · SF03 `022-distributed-auth-routing-capacity` · SF04 `023-reliable-usage-events` · SF05 `024-ha-deploy-rollout-rollback` |
| 身份与壳 | SF06 `025-unified-phone-auth` · SF07 `026-single-session-auth-hardening` · SF08 `027-web-design-system-shell` · SF09 `028-workspace-switch-authorization` |
| Project 与供给 | SF10 `029-buyer-project-lifecycle` · SF11 `030-provider-binding` · SF12 `031-project-proxy-key-scope` · SF14 `032-provider-connection-credentials` · SF15 `033-connection-verify-health` · SF16 `034-supply-mode-lifecycle` |
| 数据面 | SF18 `035-native-passthrough-kernel` · SF22 `036-stream-file-async-affinity` · SF19 `037-openai-stable-dataplane` · SF20 `038-anthropic-stable-dataplane` · SF21 `039-vertex-stable-dataplane` |
| 计量与路由 | SF26 `040-native-spend-usage-capture` · SF27 `041-versioned-rates-quotes` · SF17 `042-seller-quote-workbench` · SF23 `043-shared-route-qualification` · SF24 `044-composite-score-routing` · SF25 `045-dedicated-binding-fail-closed` |
| 账本与运营 | SF28 `046-immutable-ledger-settlement` · SF29 `047-async-settlement-recon` · SF13 `048-project-budget-guide` · SF30 `049-admin-identity-rbac` · SF31 `050-ops-admin-console` · SF32 `051-observability-slo-alerts` · SF33 `052-capacity-resilience` · SF34 `053-release-gates` |

V0.1 功能仍在 `specs/001`–`019`。
