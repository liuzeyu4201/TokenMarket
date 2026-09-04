[中文](README.md) | **English**

# Product, research, and specs

Product narrative and engineering specs **are not copied into `docs/`**. This page classifies three source trees.

On conflict: **constitution > V0.2 outline and cross-cutting rules > SF / Spec Kit feature specs > PRD > architecture/language standards**. See [`项目开发/V0.2/V0.2_0831/README.md`](../../项目开发/V0.2/V0.2_0831/README.md).

## Product definition (`项目开发/`)

Full index: [`项目开发/README.md`](../../项目开发/README.md)

| Document | Purpose |
|----------|---------|
| [V0.2 implementation index](../../项目开发/V0.2/V0.2_0831/README.md) | V0.2 scope, precedence, locked decisions |
| [V0.2 outline](../../项目开发/V0.2/V0.2_0831/V0.2_0831_实现总纲.md) | Goals, journeys, success criteria |
| [Feature matrix](../../项目开发/V0.2/V0.2_0831/功能清单与依赖矩阵.md) | SF01–SF34 and batches |
| [PRD](../../项目开发/产品需求文档（PRD）.md) | Long-term positioning (money-loop passages yield to the V0.2 outline) |
| [Roadmap](../../项目开发/产品迭代路线图.md) | Multi-version themes; recharge/withdraw conflict with V0.2 |
| [V0.1 spec index](../../项目开发/V0.1/V0.1_0712/specs/README.md) | Historical SF01–SF19 |
| [Architecture and layout](../../项目开发/1-项目架构与目录结构.md) | Target architecture |

## Market research (`产品调研/`)

Full index: [`产品调研/README.md`](../../产品调研/README.md)

| Directory | Purpose |
|-----------|---------|
| `商业计划书/` | Business-plan chapters, bound edition, [promo deck](../../产品调研/商业计划书/TokenMarket_宣传PPT.pptx) |
| `竞品分析/` | Gateways, resale, domestic market, indirect competitors |
| `厂商调研/` | Model and platform vendors |
| `战略与生态规划/` | Coding Plan ecosystem and synthesis |

## Implementation specs (`specs/`)

Spec Kit directories `specs/NNN-short-kebab/` match the Git branch name. Each holds `spec.md`, `plan.md`, `tasks.md`, contracts, and evidence.

V0.2 SFs map 1:1 onto `specs/` (ids follow dependency batches, not SF number order):

| Batch | SF → `specs/` |
|-------|----------------|
| Engineering | SF01 `020` … SF05 `024` |
| Identity and shell | SF06 `025` … SF09 `028` |
| Project and supply | SF10 `029` … SF16 `034` (SF13 is later `048`) |
| Data plane | SF18 `035`, SF22 `036`, SF19–21 `037`–`039` |
| Metering and routing | SF26–27 `040`–`041`, SF17 `042`, SF23–25 `043`–`045` |
| Ledger and ops | SF28–29 `046`–`047`, SF13 `048`, SF30–34 `049`–`053` |

The full table is in the Chinese sibling. V0.1 features remain `specs/001`–`019`.
