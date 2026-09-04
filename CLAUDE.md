# 仓库指南

## 项目结构与模块组织

本仓库当前以规格与工程标准为主。变更架构或代码前须阅读
`.specify/memory/constitution.md`。产品调研位于
`产品调研/`；实现标准、PRD、路线图与 V0.1 规格位于
`项目开发/`。

应用代码必须遵循已文档化的 monorepo 布局：`services/proxy-gateway/` 为
Go 入口，`services/{api,billing,admin}-service/` 为 FastAPI 服务，`frontend/` 为
React 应用，`shared/` 为版本化契约，`infra/`/`ops/` 为部署、
监控、迁移与运行手册。测试保留在各组件既定测试根目录内。

## Agent skills

项目技能以 `.agents/skills/` 为权威副本，并镜像到
`.claude/skills/`、`.cursor/skills/`、`.codex/skills/`、
`.grok/skills/`、`.kimi-code/skills/`。进行中的 merge/rebase 冲突用
`resolving-merge-conflicts`；合并提交之后的静默丢失用 `merge-reconciler`。

## 构建、测试与开发命令

根 Makefile 是实现脚手架阶段的必需工作流入口：

- `make start` / `make stop`：本地默认入口 — SF02 中间件加五个主机
  应用进程。`make dev` / `make dev-down`：仅中间件
  （PostgreSQL 15、Redis 7、Grafana OSS）。Kafka 不在 SF02 依赖
  集内。本地开发中业务服务为主机进程 — 永不加入
  `compose.local.yml`。
- `make deploy` / `make deploy-down`：按 ADR 003 的测试/生产全栈（中间件 + 五个
  应用镜像）。必须显式 `mode=test|prod`。Phase 1 在 Docker 前
  失败关闭（fail-closed）；资产位于 `infra/docker/compose.{middleware,app,deploy}.yml`。
- `make test`：运行全部 Go、Python 与前端测试套件。
- `make lint`：跨组件运行静态分析与类型检查。
- `make fmt`：应用仓库格式化工具。
- `make build`：构建全部服务镜像。
- `make migrate`：应用已评审的 Alembic 迁移。

当已有 Make 目标可扩展时，不得新增一次性脚本。在 Makefile
落地前，仅文档变更需要结构与链接校验，而非应用测试。

## 编码风格与命名约定

Go 代码必须通过 `gofmt`、`go vet` 与 `golangci-lint`；包名小写，
导出标识符使用 `PascalCase`。Python 使用四空格、`snake_case`、类型注解、
Black、isort、flake8 与 mypy。React 使用严格 TypeScript、ESLint 与 Prettier；组件命名
`PascalCase.tsx`，hooks 命名 `useSomething.ts`。保持服务边界，并在消费者之前定义 HTTP/事件
契约。

## 测试指南

实现前先写测试。Go 使用 `testing` 包并开启竞态检测与覆盖率；
Python 使用 pytest、pytest-asyncio 与 testcontainers。Python 测试命名为 `test_<behavior>.py`，
Go 测试命名为 `*_test.go`。变更的 Go 与 Python 领域包要求至少 80% 行
覆盖率，并对授权、幂等、并发与迁移做直接负向测试。

## 提交与 Pull Request 指南

遵循 Conventional Commits（例如 `feat: add gateway health check` 或
`docs: clarify migration policy`）。PR 必须说明范围、链接相关
规格或 issue、列出验证验收证据、标明契约/schema/安全
影响，并包含上线与回滚说明。可见前端变更须附截图。

### 分支命名

权威规则见 `ops/runbooks/workflow.md`。摘要：

| 类型 | 形式 | PR 合入 |
|------|---------|---------|
| 生产线 | `master`（固定） | — |
| 测试线 | `master-dev`（固定） | — |
| Spec Kit 功能 | `NNN-short-kebab` **=** 仅 `specs/NNN-short-kebab/` | `master-dev` |
| 产品改动（无 Spec Kit 功能） | `feat/<slug>` | `master-dev` |
| 缺陷修复 | `fix/<slug>` | `master-dev` |
| 生产热修 | `hotfix/<slug>`（从 `master`） | `master`，然后回合并 |
| 文档 / 杂务 / 重构 | `docs|chore|refactor/<slug>` | `master-dev` |

规则：小写 ASCII kebab-case；无空格/下划线；推荐 ≤ 50 字符；
永不使用环境名（`local`/`test`/`prod`）作为分支；永不在没有匹配
`specs/NNN-.../` 目录时发明编号 `NNN-...` 分支；已有编号 Spec Kit 功能时永不
使用 `feat/002-...` / `feature/002-...`。
PR 合入 `master-dev`。测试验证后经评审 PR 晋升到
`master`。合入 `master` 的 hotfix 必须
回合并到 `master-dev`。Make 环境选择保持显式
`mode=local|test|prod`，永不从 Git 分支名推断；见
`ops/runbooks/workflow.md` 与 `shared/contracts/repository-workflow/v1/`。

## 安全与配置

永不提交 `.env.*`、凭据、提供商密钥或生产数据。仅用
安全占位符更新 `.env.example`。密钥必须加密、从遥测中脱敏，并通过
环境变量或经批准的密钥提供方注入。

## 活动功能上下文

- `001-repository-workflow-baseline`：规划产物位于
  `specs/001-repository-workflow-baseline/plan.md`，开发者契约在其
  `contracts/` 目录下。
- 计划维护的工具链为 Go 1.25.14、带独立 workflow-tool
  锁与每服务 `uv.lock` 的 Python 3.11.15，以及带 npm 锁文件的 Node 24.18.0 LTS；依赖或工具
  升级仍为经评审变更。
- 根 Makefile 仍是唯一公共工作流。除七个公共动作外，
  还需要稳定的 `bootstrap` 与 `type-check` 支持命令；bootstrap 仅准备
  已提交锁的依赖，永不安装系统工具或重写锁。
- GitHub Actions 是调用 `make ci` 的只读薄适配层；组件命令与
  质量门禁不得在 CI YAML 中重复。CI 迁移验收证据使用固定隔离的
  PostgreSQL 15 容器，按 API→Billing 做前向/回退/重试/head 恢复。
- SF02 公共激活（T074）已完成：`make dev` / `make dev-down` 与
  `make start` / `make stop` 运行真实本地中间件生命周期；公共
  工作流事件默认使用 v2 标准封装。历史
  `SF02_NOT_READY` 仅作为弃用窗口文档保留（T074 激活前的历史门禁语境）。
- SF01 仅脚手架运维健康、指标、测试与不可变构建；不得添加
  买家、卖家、提供商 Key、代理、计量、计费或管理类业务行为。
- `002-local-dependency-lifecycle`：设计与验收证据位于
  `specs/002-local-dependency-lifecycle/`；ADR 002 实现验证为
  **Verified**。双平台生命周期验收证据（T069/T070）与负责人易用性
  验收证据（T071）记录于 `evidence/`。
- SF02 限于经评审多平台 OCI index digest 固定的 PostgreSQL 15.18、Redis 7.2 与 Grafana OSS 13.0。
  它推导 `tokenmarket-<workspace-path-hash>` 项目
  所有权，仅接受被忽略 `.env.local` 中的回环
  `DATABASE_URL`/`REDIS_URL`/`GRAFANA_URL` 事实，使用碰撞检查的全工作区指纹与 Compose 管理的非 root
  密钥文件，经 stdin 管道传入已验证已提交 Compose 字节与安全哈希运行时
  项目目录，使 Compose 标签不暴露工作区路径，串行化生命周期
  操作，保留 PostgreSQL/Redis 命名卷，并在普通 down 时为 Grafana 提供显式 tmpfs
  存储。
- SF02 中仅 API Service 与 Billing Service 获得感知 PostgreSQL 的就绪检查。其 liveness
  保持独立；Gateway 与 Admin Service 不得获得未声明依赖探针，且
  无业务服务成为 `make dev` 的一部分。
- 分层 Compose 部署（分支 `feat/layered-compose-deploy`，**不是** Spec Kit
  `specs/NNN-...` 功能）：ADR 003（`docs/decisions/003-layered-compose-deploy.md`），
  契约位于 `shared/contracts/deploy-environment/v1/`，compose 资产位于
  `infra/docker/compose.{middleware,app,deploy}.yml`。公共入口：`make deploy` /
  `make deploy-down`，`mode=test|prod`。勿把业务服务扩进 `compose.local.yml`，或
  恢复根级全栈 compose 草图。
