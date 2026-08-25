# TokenMarket

> 可验证、可复现的 AI 服务与 Token 交易市场工程基线。

TokenMarket 是一个面向 AI 流量代理与 Token 交易场景的 monorepo 工程基线。当前处于 **V0.1** 阶段：工程工作流基线（SF01）与本地依赖生命周期（SF02，T074 已激活）已就绪；买家、卖家、提供商 Key、代理路由、计量计费等业务能力仍在后续功能中推进，尚未作为完整产品交付。

## 当前阶段

**SF01 — 仓库工程工作流基线**（已交付）与 **SF02 — 本地依赖生命周期**（T074 已激活）

- 单一根入口：`make help`、`make start` / `make stop`、`make dev` / `make dev-down`、`make fmt`、`make lint`、`make test`、`make build`、`make migrate`、`make ci`
- 八个职责清晰的组件边界：Go 网关、三个 Python 服务、React 前端、共享契约、基础设施定义、运维资产
- 本地与 GitHub Actions 使用同一套 `make ci` 质量门禁
- 安全配置、秘密扫描、依赖扫描与生产审批契约已就位
- 所有必需组件具备真实可运行的最小骨架与冒烟测试
- 本地 PostgreSQL / Redis / Grafana 由 `make dev`（或默认的 `make start`）管理；业务进程在本机运行

## 技术栈

| 层级 | 技术 |
|------|------|
| 网关 | Go 1.25.14、Gin、Prometheus |
| 后端服务 | Python 3.11.15、FastAPI、Pydantic、SQLAlchemy、Alembic、asyncpg |
| 前端 | React 18、TypeScript（strict）、Vite、Vitest、ESLint、Prettier |
| 工程工具 | uv、npm、Docker、Make、GitHub Actions |
| 可观测与基础设施 | Prometheus 指标；本地 Grafana / PostgreSQL / Redis 生命周期由 SF02 管理 |

## 快速开始

本地启动的默认入口：

```bash
make start
make stop
```

首次准备、配置、迁移、当前 SF02 激活状态和故障恢复见
[`QUICKSTART.md`](QUICKSTART.md)。质量门禁仍通过 `make test`、`make lint`、
`make build` 和 `make ci` 执行。

## 项目结构

```text
.
├── services/proxy-gateway   # Go 入口网关（健康、metrics、request ID）
├── services/api-service     # 核心 API 服务与首个迁移所有者
├── services/billing-service # 计费服务与第二个迁移所有者
├── services/admin-service   # 管理服务（无数据库所有权）
├── frontend                 # React 18 可访问前端骨架
├── shared                   # 版本化契约与共享验证工具
├── infra                    # 基础设施定义（含本地 Compose 与部署分层资产）
├── ops                      # 迁移所有权、运行手册、监控、备份与本地依赖清单
├── tools/workflow           # 仓库工作流 CLI（事件、清单、模式、扫描）
├── tests/workflow           # 根级工作流契约测试
└── docs/decisions           # 架构决策记录（ADR）
```

## 公开工作流入口

| 命令 | 用途 |
|------|------|
| `make start` / `make stop` | **本地默认入口**：中间件 + 五个主机应用进程；每次启动重读 `.env.local`，配置变化时重启对应应用 |
| `make dev` / `make dev-down` | **本地中间件**正式公共入口（PostgreSQL/Redis/Grafana；T074 已激活）；业务进程在本机运行（见 `ops/runbooks/local-environment.md`） |
| `make deploy` / `make deploy-down` | **测试/生产**全栈（中间件 + 五个业务镜像）；必须 `mode=test\|prod`。部署适配器落地前失败关闭（fail-closed）（ADR 003 / `ops/runbooks/deploy.md`） |
| `make fmt` | 应用仓库格式化工具 |
| `make lint` | 汇总静态分析、类型检查与边界检查 |
| `make test` | 汇总所有组件自动化测试 |
| `make build` | 构建五个服务镜像与三个确定性资产包 |
| `make migrate` | 按所有者顺序执行已评审迁移 |
| `make ci` | 本地复现 hosted `quality-gate` 的完整顺序 |

**分层约定**：本地开发默认使用 `make start`；中间件单独操作保留
`make dev` / `make dev-down`，应用进程单独操作使用 `scope=apps`。测试/生产主机 =
`make build` 后 `make deploy mode=…`。勿把业务服务写入
`infra/docker/compose.local.yml`。

## 安全与合规

- 真实配置只能通过 `.env.local` 等被忽略文件注入；`.env.example` 仅含不可用占位符。
- 秘密扫描（gitleaks）、Go 漏洞扫描（govulncheck）、Python 依赖扫描（pip-audit）、npm audit 均失败关闭。
- 生产动作必须通过 `mode=prod` 显式选择并经过独立审批。
- 详见 [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md)。

## 分支与环境

| 分支 | 角色 |
|------|------|
| `master` | 生产分支（始终可发布；生产部署代码源） |
| `master-dev` | 测试环境部署分支（功能先合入并验证） |

### 分支命名

| 类型 | 形式 | 示例 |
|------|------|------|
| Spec Kit 功能（有 `specs/`） | `NNN-short-kebab`，与 `specs/` 目录名一致 | `002-local-dependency-lifecycle` |
| 产品改动（无 Spec Kit 功能） | `feat/<slug>` | `feat/layered-compose-deploy` |
| 缺陷修复 | `fix/<slug>` | `fix/api-readiness-timeout` |
| 生产热修 | `hotfix/<slug>`（从 `master` 拉出） | `hotfix/migrate-approval` |
| 文档 / 杂务 / 重构 | `docs|chore|refactor/<slug>` | `docs/local-env-runbook` |

要求：小写 ASCII、kebab-case、推荐 ≤ 50 字符；禁止用环境名当分支名；**没有** `specs/NNN-...` 时不得造 `NNN-...` 分支；已有编号规格时禁止 `feat/002-...` / `feature/002-...`。PR 默认合入 `master-dev`，测试验证后再晋升到 `master`。迁移/部署仍须显式 `mode=local|test|prod`，**不**根据分支名推断环境。完整规则见 [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md)。

## 持续集成

`.github/workflows/ci.yml` 是一个只读薄适配层，在 `master` / `master-dev` 的 PR 与 push 上触发，仅执行：

```bash
make ci
```

所有项目逻辑保留在根 `Makefile` 与 `tools/workflow/` 中，CI 平台可替换而无需修改项目行为。

## 状态

- `make test` / `make lint` / `make fmt-check`：通过
- `make ci`：当前因已知 `starlette 0.45.3` 依赖漏洞失败关闭；修复前不启用 required check
- 文档与验收证据：`specs/001-repository-workflow-baseline/checklists/`

## License

Proprietary — 未经许可不得使用、复制或分发。
