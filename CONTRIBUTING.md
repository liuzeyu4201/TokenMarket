**中文** | [English](CONTRIBUTING.en.md)

# 贡献指南

TokenMarket 以 [Apache License 2.0](LICENSE) 开源。本文说明如何改代码、命名分支、开 PR。权威细则：[ops/runbooks/workflow.md](ops/runbooks/workflow.md)。

## 开发循环

1. 从健康的 `master-dev` 拉出分支（生产热修从 `master`）。
2. 先规格与测试，再实现（宪章：合并前要有测试证据）。
3. 根入口：`make fmt`、`make lint`、`make test`；合入前可复现 `make ci`。
4. 使用 [Conventional Commits](https://www.conventionalcommits.org/)（例如 `feat: add gateway health check`、`docs: classify documentation hub`）。
5. PR 合入 `master-dev`。测试验证后再晋升 `master`。

## 分支

| 类型 | 形式 | 合入 |
|------|------|------|
| 生产线 | `master`（固定） | — |
| 测试线 | `master-dev`（固定） | — |
| Spec Kit 功能 | `NNN-short-kebab` = 仅 `specs/NNN-short-kebab/` | `master-dev` |
| 无 Spec Kit 的产品改动 | `feat/<slug>` | `master-dev` |
| 缺陷 | `fix/<slug>` | `master-dev` |
| 生产热修 | `hotfix/<slug>`（从 `master`） | `master`，然后回合并 |
| 文档 / 杂务 / 重构 | `docs\|chore\|refactor/<slug>` | `master-dev` |

规则：小写 ASCII kebab-case；推荐 ≤ 50 字符；分支名不编码 `local` / `test` / `prod`。没有对应 `specs/NNN-.../` 时不得发明 `NNN-...` 分支；已有编号规格时不得使用 `feat/002-...`。

环境一律显式 `mode=local|test|prod`，不从分支名推断。

## PR 应包含

- 范围与相关规格 / issue
- 验证证据（命令与结果）
- 契约、schema、安全影响
- 上线与回滚说明
- 可见前端变更的截图或等价说明

## 质量门禁

GitHub Actions 只调用 `make ci`。不要在 workflow YAML 里复制组件命令。密钥、`.env.local`、生产数据不得提交。

新服务、存储、协议或跨服务依赖必须带 [ADR](docs/decisions/README.md)。
