[中文](README.md) | **English**

# Product, research, and specs

Product narrative and engineering specs **are not copied into `docs/`**. This page classifies three source trees.

On conflict follow the order in [`项目开发/V0.1/V0.1_0712/specs/README.md`](../../项目开发/V0.1/V0.1_0712/specs/README.md): constitution > V0.1 roadmap scope > weekly feature spec > PRD > architecture/language standards.

## Product definition (`项目开发/`)

Full index: [`项目开发/README.md`](../../项目开发/README.md)

| Document | Purpose |
|----------|---------|
| [PRD](../../项目开发/产品需求文档（PRD）.md) | Positioning, users, value, success metrics |
| [Roadmap](../../项目开发/产品迭代路线图.md) | V0.1 → V3.0 themes and boundaries |
| [V0.1 spec index](../../项目开发/V0.1/V0.1_0712/specs/README.md) | SF01–SF19 scope and dependencies |
| [Architecture and layout](../../项目开发/1-项目架构与目录结构.md) | Target architecture |
| Go / Python / frontend standards | `项目开发/2–4-*.md` |

## Market research (`产品调研/`)

Full index: [`产品调研/README.md`](../../产品调研/README.md)

| Directory | Purpose |
|-----------|---------|
| `商业计划书/` | Business-plan chapters and bound edition |
| `竞品分析/` | Gateways, resale, domestic market, indirect competitors |
| `厂商调研/` | Model and platform vendors |
| `战略与生态规划/` | Coding Plan ecosystem and synthesis |

## Implementation specs (`specs/`)

Spec Kit feature directories `specs/NNN-short-kebab/` match the Git branch name. Each holds `spec.md`, `plan.md`, `tasks.md`, contracts, and evidence.

| Batch | Features |
|-------|----------|
| Engineering baseline | `001` repository workflow · `002` local dependencies |
| Identity | `003` registration · `004` login session · `005` role isolation |
| Platform and credentials | `006` Volcano validation · `007` Volcano compat · `008` seller onboard · `009` seller lifecycle |
| Proxy path | `010` buyer proxy key · `011` proxy auth · `012` non-stream · `013` key pool · `014` capacity · `015` stream |
| Metering and ops | `016` key health · `017` usage records · `018` structured logs · `019` metrics dashboard |
