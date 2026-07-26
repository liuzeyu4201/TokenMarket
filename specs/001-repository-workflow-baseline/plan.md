# Implementation Plan: 仓库工程工作流基线

**Branch**: `001-repository-workflow-baseline` *(功能标识符；未运行分支钩子)* | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)

**Input**: 功能规格来自 `/specs/001-repository-workflow-baseline/spec.md`

## Summary

创建 TokenMarket 首个可执行 monorepo 基线：八个显式组件边界、五个最小可部署服务/前端脚手架、三个可验证资产组件、带稳定锁定依赖 bootstrap 与 type-check 命令的根 Make 工作流、安全配置与迁移模式契约，以及实际阻塞式 CI 适配层。每个必需组件将执行真实的 format、type、lint、smoke-test 与 build 工作，同时不暴露任何 TokenMarket 业务行为。

实现以契约优先、测试优先。一个小型、有明确归属的 repository-workflow 工具读取版本化组件清单并输出经校验的 JSON Lines 证据；根 Makefile 仍是唯一公共入口。GitHub Actions 是只读薄适配层，运行 `make ci`。SF02 仍负责真实本地依赖生命周期，因此在该能力交付前，`dev` 与 `dev-down` 以 `SF02_NOT_READY` 尽早失败且无副作用。

## Technical Context

**Language/Version**: 编排使用兼容 GNU Make 3.81 的语法与 POSIX shell；`proxy-gateway` 使用 Go 1.25.12；工作流工具与三个服务使用 Python 3.11.15；前端使用 Node 24.18.0 LTS 与严格 TypeScript；契约与 CI 使用 YAML/JSON/JSON Schema/OpenAPI

**Primary Dependencies**: Gin 与兼容 Prometheus 的 Go 指标；Python 服务使用 FastAPI、Pydantic、Uvicorn 与 Prometheus client；前端使用 React 18、Vite、Vitest/Testing Library、ESLint 与 Prettier；一个 uv 锁定的仓库工作流工具环境，加上每个 Python 服务的独立 uv 锁；带 `package-lock.json` 的 npm；Docker BuildKit；GitHub Actions 薄适配层；安全门禁使用 Gitleaks、govulncheck、pip-audit、npm audit 与 Trivy

**Storage**: 无 TokenMarket 业务存储或 schema。持久工程事实为 Git 跟踪的组件/迁移清单、schema、锁文件与文档。CI 仅使用带合成凭据的隔离 PostgreSQL 15 实例做迁移往返证据。工作流事件/构建报告为临时数据，且不得包含密钥或个人数据。

**Testing**: 带竞态检测与覆盖率的 Go `testing`；仓库工作流工具与各 Python 服务使用 pytest/pytest-asyncio；前端使用 Vitest 与 Testing Library；`tests/workflow/` 中的仓库工作流契约/负向测试；固定 PostgreSQL 15 容器的迁移前向/回退/重试/head 恢复集成；容器运行时健康冒烟；schema、链接、边界与确定性归档测试

**Target Platform**: macOS 与 Linux 开发主机；Linux 容器；GitHub 托管的 `ubuntu-24.04` CI。服务镜像在 SF01 中为当前已验证平台构建；多架构发布不在范围内。

**Project Type**: 多语言 monorepo，包含开发者 CLI/工作流、四个后端服务脚手架、一个 Web 前端脚手架、版本化契约与基础设施/运维资产

**Performance Goals**: `make help` 在 2 秒内完成；缺失/不支持的工具或无效配置/模式在副作用前 5 秒内失败；增量命令永不无条件重装全部依赖；所有 SC-001–SC-012 阈值在自动化或文档化验证中被行使

**Constraints**: 根 Makefile 是唯一公共工作流；`bootstrap` 在工具链校验后仅安装锁解析的项目依赖，永不安装系统工具或重写锁；无业务端点或数据表；无真实凭据或 `.env.*`（安全示例除外）；无跨服务存储/导入；无固定绝对路径；支持含空格/中文的路径；脏工作树格式化不得 reset/delete/超出范围修改；`mode` 为精确小写且生产需要第二道门禁；`dev`/`dev-down` 在 SF02 前不得检查 Docker；CI 只读且不发布或部署

**Scale/Scope**: 八个必需边界、五个不可变服务/前端镜像、三个确定性资产归档、七个稳定公共目标加上稳定的 `bootstrap`/`type-check` 与受控支持目标、两个迁移负责人、一个阻塞式 CI 作业与四个开发者/运维契约族

**Affected Components**: `services/proxy-gateway/`、`services/api-service/`、`services/billing-service/`、`services/admin-service/`、`frontend/`、`shared/`、`infra/`、`ops/`、根工作流/工具、文档与 `.github/workflows/`

**Contracts**: 开发者 CLI/退出码/输出契约、工作流事件 JSON Schema、组件清单 JSON Schema、环境模式契约、迁移负责人清单 JSON Schema、CI 门禁契约与最小服务健康 OpenAPI。不引入 TokenMarket 买家/卖家/提供商 HTTP 或事件契约。

**Data & Migrations**: `api-service` 然后 `billing-service` 被声明为迁移负责人；`admin-service` 为非负责人且不能访问其存储。SF01 初始化真实 Alembic 图但不含业务表。离线 `migrate-check` 校验单 head、命名、upgrade/downgrade 与回退链接；CI 使用 PostgreSQL 15 做前向/回退/重试。`make migrate` 永不启动数据库，并在配置或网络访问前校验 `mode`/审批。

**Security & Privacy**: 仅合成配置；除安全示例外忽略 `.env` 与 `.env.*`；密钥值永不提交、记录、缓存、放入 fixture 或 build args。CI 权限为 `contents: read`，checkout 凭据不持久化，无可用密钥，不受信任的 PR 使用 `pull_request`。扫描失败关闭 (fail-closed)；例外需要 ID、负责人、审批、issue 与到期时间。

**Observability & Reliability**: 工作流发出脱敏 JSONL 步骤事件，含 run ID、组件、动作、状态、稳定代码与时长，以及可访问的纯文本。后端脚手架提供请求 ID、结构化安全日志、`/health/live`、`/health/ready`、`/metrics`；就绪检查无 SF02 依赖。必需动作快速失败、可安全重试，且永不将跳过的工作报告为通过。

**Deployment & Rollback**: SF01 创建可构建镜像与 CI，但不执行生产部署或发布。上线为经评审 PR、CI 激活与要求稳定 `quality-gate` 的仓库规则集。回滚为经评审的 revert PR，保持必需作业名稳定；无业务数据变更。工具升级将工作流 SHA、版本文件与适配器一并回滚。

## Constitution Check

*GATE：在 Phase 0 前通过，并在 Phase 1 设计后复核。*

### Pre-Research Gate

| 门禁 | 状态 | 证据 / 决策 |
|------|--------|---------------------|
| Architecture and ownership | PASS | 仅使用 constitution 批准的边界；工作流工具为仓库工具，非新的运行时服务；无跨服务存储/导入 |
| Contracts and compatibility | PASS | 开发者与健康契约在实现前设计；公共 Make 目标保持稳定 |
| Security and privacy | PASS | 无真实密钥、生产值或可写 CI；规划扫描与副作用前模式校验 |
| Data correctness | PASS | 无业务数据；显式迁移负责人、顺序、离线校验与 PostgreSQL 往返/回退证据 |
| Testing | PASS | 测试/负向 fixture 先于每个适配器与脚手架；定义竞态/类型/契约/迁移/容器证据 |
| Operations | PASS | 分离 live/ready、指标、请求 ID、安全日志、工作流证据、失败代码与 runbook 负责人已规划 |
| Delivery | PASS | 锁定的维护工具链、不可变镜像、实际阻塞式 CI、回滚与可追溯性均包含在内 |

无门禁需要例外。GitHub Actions 是新的交付适配层而非运行时服务；因仓库尚无现有远程且选择必须可替换，仍规划 ADR。

### Post-Design Gate

| 门禁 | 状态 | Phase 1 证据 |
|------|--------|------------------|
| Architecture and ownership | PASS | [data-model.md](./data-model.md) 定义八个边界、动作归属与禁止依赖 |
| Contracts and compatibility | PASS | [contracts/](./contracts/) 定义 Make、事件、组件、模式、迁移、CI 与健康行为及版本化 |
| Security and privacy | PASS | 环境/CI 契约在密钥或资源访问前失败；quickstart 仅使用合成数据 |
| Data correctness | PASS | 迁移实体、负责人清单 schema 与隔离往返程序明确；不存在业务 schema |
| Testing | PASS | [quickstart.md](./quickstart.md) 加下方验证矩阵覆盖正向、负向、恢复与可复现性证据 |
| Operations | PASS | 健康 OpenAPI、JSONL 事件 schema、稳定代码与 runbook 路径已定义 |
| Delivery | PASS | CI 门禁、不可变构建证据、激活与 revert 程序已规定 |

设计后结果：**PASS — 无未解决澄清或无正当理由的 constitution 违反。**

## Project Structure

### Documentation (this feature)

```text
specs/001-repository-workflow-baseline/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── make-workflow.md
│   ├── workflow-event.schema.json
│   ├── component-manifest.schema.json
│   ├── environment-mode.md
│   ├── migration-manifest.schema.json
│   ├── ci-gates.md
│   └── service-health.openapi.yaml
└── tasks.md                       # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
Makefile                            # Only public workflow entry
README.md                           # Checkout-to-first-verification guide
.env.example                       # Safe names/comments/placeholders only
.gitignore
.tool-versions                     # Maintained language/tool version source
.github/
├── workflows/ci.yml               # Thin adapter: make ci
├── dependabot.yml                 # Optional platform supplement, not core gate
└── CODEOWNERS                     # Workflow/contract ownership
docs/
├── api/README.md
└── decisions/
    └── 001-github-actions-ci-adapter.md
tools/workflow/                    # Maintained internal workflow tool, not a one-off script
├── __init__.py
├── pyproject.toml                 # Locked repository-tool test/format/type environment
├── uv.lock
├── cli.py                         # Manifest orchestration, safe output, mode validation
├── events.py
├── manifest.py
├── migrations.py                 # Offline checks and isolated PostgreSQL 15 round-trip
├── mode.py
└── security.py
tests/workflow/
├── test_foundational_contracts.py
├── test_command_contract.py
├── test_component_manifest.py
├── test_dirty_format.py
├── test_migrations.py
├── test_mode.py
├── test_paths.py
├── test_sf02_transition.py
└── fixtures/
ops/workflow/
├── components.json                # Single component/action fact source
└── toolchains.json                # Version/integrity fact source
services/
├── proxy-gateway/
│   ├── cmd/gateway/main.go
│   ├── internal/httpserver/
│   │   ├── server.go
│   │   └── server_test.go
│   ├── internal/observability/
│   ├── go.mod
│   ├── go.sum
│   ├── .golangci.yml
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── Makefile                   # Internal adapter only
│   └── README.md
├── api-service/
│   ├── app/{__init__.py,main.py,health.py,observability.py}
│   ├── tests/test_health.py
│   ├── alembic/{env.py,versions/}
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── Makefile
│   └── README.md
├── billing-service/               # Same minimal Python shape + owned Alembic graph
└── admin-service/                 # Same runtime shape, no migration ownership
frontend/
├── src/{main.tsx,App.tsx,App.test.tsx}
├── index.html
├── nginx.conf
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── vitest.config.ts
├── eslint.config.js
├── .prettierrc
├── Dockerfile
├── .dockerignore
├── Makefile
└── README.md
shared/
├── contracts/
│   ├── README.md
│   └── _meta/contract-manifest.schema.json
├── tests/
├── Makefile
└── README.md
infra/
├── docker/README.md
├── nginx/README.md
├── grafana/README.md
├── kafka/README.md
├── tests/
├── Makefile
└── README.md
ops/
├── migrations/{owners.json,README.md}
├── monitoring/README.md
├── backup/README.md
├── runbooks/{workflow.md,migrations.md}
├── tests/
├── Makefile
└── README.md
```

**Structure Decision**: 保留 constitution 批准的每个运行时边界，但仅创建具有即时可验证价值的层。五个可部署组件获得最小健康/指标运行时代码；`shared`、`infra` 与 `ops` 获得版本化资产、负向测试与确定性包。不创建空的业务/领域包、复制的共享模型、跨服务仓库或占位业务路由。

## Implementation Strategy

### Phase A — 契约与失败的工作流测试

1. 在创建 CI 配置前添加 GitHub Actions 适配器 ADR。
2. 构建隔离的工作流测试夹具，并为缺失或无效的运行时契约副本、组件/工具链清单与迁移负责人清单编写失败测试。
3. 仅在那些基础测试因缺失运行时事实而失败后，再从 Phase 1 schema 物化组件/工具链/迁移清单。
4. 先为命令发现、锁定/幂等 bootstrap、显式 type-check、必需动作绑定、JSONL 事件、安全路径、脏格式化、模式来源、生产审批与 SF02 过渡编写根工作流测试。
5. 为缺失组件、空适配器、零测试、边界违反、契约漂移、无效模式、密钥检测与迁移图错误添加负向 fixture。

**Exit evidence**: 测试按预期对缺失工作流/脚手架行为失败，并校验 Phase 1 契约。

### Phase B — 根工作流与安全配置

1. 为 `tools/workflow` 初始化专用 uv 锁定环境；在可行处用 Python 3.11 标准库实现小型包。它是带 pytest、format 与 type 证据的维护型内部工具，而非一次性脚本。
2. 实现根 Make 目标与内部组件适配器，不重复组件列表。`bootstrap` 先校验系统工具链，再仅执行冻结的 Go/uv/npm 依赖准备；`type-check` 可独立调用并仍是 `lint` 的一部分。
3. 添加安全 `.env.example`、忽略规则、工具链预检、脱敏 JSONL/纯文本输出与链接/结构检查。
4. 在配置/资源访问前实现 `mode=local|test|prod` 来源校验与生产双重门禁。
5. 实现在 Docker/配置访问前失败的 `dev`/`dev-down` 阻塞适配器。

**Exit evidence**: 工作流契约测试通过；两次冻结 bootstrap 运行保持锁文件不变；`type-check`、help 与预检阈值通过；被拒绝动作的副作用快照保持不变。

### Phase C — 最小组件脚手架

1. 先写 Go 测试，再实现 gateway 健康/就绪/指标、请求 ID 与结构化日志。
2. 先写 pytest 测试，再在每个 Python 服务中独立实现相同运维契约；仅对 API 与 billing 负责人初始化 Alembic。
3. 实现最小可访问前端页面、测试与非特权运行时健康行为。
4. 实现 shared/infra/ops 校验器、负向测试与确定性包。
5. 添加每组件内部 Make 适配器、锁文件、Dockerfile 与 `.dockerignore` 文件。

**Exit evidence**: 全部八个组件产生真实 fmt/lint/test/build 证据；五个镜像以非 root 健康运行；未知业务路径返回 404。

### Phase D — 迁移、安全与可复现性门禁

1. 添加迁移负责人对账与离线图检查，然后用带合成凭据的固定 PostgreSQL 15 镜像实现 `migrate-integration-check`。它必须按 API 然后 Billing 运行前向迁移、回退、重试与最终 head 恢复，不依赖 `make dev` 或共享数据库。
2. 通过根目标添加全历史密钥扫描、锁定依赖扫描与不可变镜像扫描。
3. 按精确版本加完整性引用固定工具、Actions 与基础镜像。
4. 在同一提交上证明确定性资产归档与重复构建。

**Exit evidence**: `make migrate-check`、`make migrate-integration-check`、`make security-check`、`make build`、运行时冒烟与 `make image-scan` 全部通过；隔离数据库回到两个声明的 head，合成负向 fixture 被检测并脱敏。

### Phase E — CI 激活与文档

1. 添加 `.github/workflows/ci.yml`，含只读权限、全历史 checkout、固定工具链/扫描器设置与唯一项目命令 `make ci`；Docker 提供隔离 PostgreSQL 与镜像冒烟环境。
2. 添加 CODEOWNERS 与仓库设置说明，用于必需 `quality-gate`、受保护的 `master` / `master-dev` 与 merge queue 兼容性。
3. 完成根/组件 README 与 ops runbook；校验全部链接。
4. 当存在 GitHub 远程时，配置规则集并证明 PR 与最终 `master` / `master-dev` 触发。在此之前工作流文件可本地测试，但托管验收未完成。

**Exit evidence**: 完整 [quickstart.md](./quickstart.md) 通过，且 PR 评审证据将每项需求链接到测试/门禁。

## Verification Matrix

| 需求领域 | 计划自动化证据 | 人工/评审证据 |
|------------------|----------------------------|------------------------|
| US1 / FR-003–014 | 命令契约、冻结 bootstrap、显式 type-check、组件动作、快速失败、预检、fmt 幂等、SF02 与迁移测试 | Help 文本与恢复评审 |
| US2 / FR-015–018 | `.env` 忽略测试、安全占位符规则、Gitleaks fixture、日志/事件脱敏、锁文件检查 | 确认 Git/历史/build args 中无真实值 |
| US3 / FR-001–002, FR-019, FR-024 | 清单 schema、结构/边界负向 fixture、契约漂移与链接检查 | ADR/负责人/兼容性评审 |
| US4 / FR-020–026 | 路径 fixture、脏工作树快照、模式来源矩阵、CI 配置契约与必需门禁测试 | 托管 PR/`master`/`master-dev` 门禁证据与规则集评审 |
| ER-001–003 | 契约版本/兼容性测试、访问前审批、固定 PostgreSQL 15 迁移前向/回退/重试/head 恢复 | 安全与迁移负责人评审 |
| ER-004–007 | Help/预检计时、重试/重复运行、JSONL schema、`NO_COLOR`、屏幕阅读器安全文本 | 记录的目标环境与恢复证据 |
| SC-001–012 | Quickstart 场景加自动化计数/计时/副作用快照 | 新开发者 15 分钟练习与托管 CI 证明 |

## Test-First Order

对每个切片，在实现前添加或更新会因缺失行为而失败的测试：

1. 在运行时事实物化前失败的基础运行时契约/清单 fixture。
2. 根工作流单元与子进程测试。
3. 组件健康/指标/请求 ID 测试。
4. 组件 lint/type/边界测试。
5. 组件构建与容器冒烟测试。
6. 迁移前向/回退/重试与无效模式测试。
7. 密钥/依赖/镜像扫描正向 fixture。
8. CI YAML 与本地/托管对等测试。

变更的 Go/Python 领域覆盖率阈值仍为 80%；SF01 不创建领域包，因此不伪造该阈值。运维脚手架包仍需要直接行为与负向断言。

## Rollout and Rollback

### Rollout

1. 在一个聚焦功能分支中合并契约、清单与测试，以及最小连贯脚手架实现。
2. 要求在干净检出上本地 `make ci`。
3. 创建托管 CI 工作流，并在启用必需检查前验证只读权限。
4. 仅在一次成功 PR 运行存在后启用 `quality-gate` 规则集，防止缺失检查死锁。
5. 验证最终 `master` SHA、不可变镜像引用与扫描证据；不推送或部署镜像。

### Rollback

- 通过同一 `quality-gate` 验证的经评审 PR 回退；永不 reset 或 force-push `master` 或 `master-dev`。
- 保持必需作业名稳定；一并回退 Action SHA、工具链文件与 Make 适配器。
- 通过 schema 提升禁用受污染缓存；关闭缓存时正确性必须保持。
- 不存在需回滚的数据库 schema 或生产资源。若迁移测试 fixture 失败，丢弃隔离实例并修复迁移图。
- 真实密钥发现在任何经评审历史修复前触发撤销/轮换与审计；CI 永不自动重写历史。

## Complexity Tracking

未规划 constitution 违反或临时例外。内部工作流包与清单由该功能对单一机器可读组件/命令事实源的核心需求所正当化；它们不引入运行时服务、数据存储或跨服务依赖。
