# Phase 0 Research: 仓库工程工作流基线

**Feature**: `001-repository-workflow-baseline`

**Date**: 2026-07-13

**Status**: Complete — all planning unknowns resolved

## 1. CI 平台与唯一质量门禁

**Decision**: 使用 GitHub Actions 作为当前 CI 薄适配层，固定 `ubuntu-24.04` runner。工作流监听面向长生命周期分支 `master`（生产）与 `master-dev`（测试环境部署线）的 `pull_request`、`push`、手动复验 `workflow_dispatch`，启用 merge queue 后增加 `merge_group`。唯一 required job 名称保持为 `quality-gate`，工作流中的项目命令只有根级 `make ci`。

**Rationale**: 规格要求实际合并阻断，而仓库目前没有 remote 可用于推导托管平台。GitHub Actions 是本功能的显式默认；把全部门禁放在根 Make 工作流中，可保证本地复现，并让未来更换托管平台时只替换 CI 适配文件。核心门禁不使用路径过滤，避免 required check 因未触发而长期等待或错误放行。

**Alternatives considered**:

- GitLab CI：能力等价，但没有 GitLab remote 或既有配置证据；若未来确定托管于 GitLab，只替换薄适配层。
- Jenkins 或自托管 runner：引入额外补丁、凭证和隔离运维，不符合 V0.1 的维护规模。
- 只提供本地 Make：违反 FR-025 的实际持续集成要求。
- 在 CI YAML 中列出各组件命令：形成第二份组件与门禁事实源。

**Follow-up design record**: 实现阶段先创建 `docs/decisions/001-github-actions-ci-adapter.md`，记录默认平台、替换边界、权限和回滚；这不改变运行时架构。

## 2. 工具链版本与依赖锁

**Decision**:

- Go 固定到受官方支持的 Go `1.25.12`，使用 Gin；提交 `go.mod`、`go.sum`，并设置 `GOTOOLCHAIN=local` 防止静默自动升级。
- Python 保持宪章允许的 `3.11.15`；仓库工作流工具与三个服务分别维护独立的 `pyproject.toml` 和 `uv.lock`，使用固定版本的 uv，以 `uv sync --frozen` 准备依赖并以 `uv run --frozen` 执行命令。
- 前端使用 Node `24.18.0` LTS、npm、React 18、Vite 和 strict TypeScript；提交 `package-lock.json`，安装只允许 `npm ci`。
- 保留既定 Python 质量工具 Black、isort、flake8、mypy；不在本功能中改用 Ruff。
- GitHub 官方 Actions 固定完整 commit SHA，并在注释中标出已验证版本；第三方扫描器使用固定版本、校验和或容器 digest。
- 各服务保持独立锁文件和 Docker build context，不使用一个跨服务大锁。

**Rationale**: 宪章要求依赖处于维护状态并允许经过测试的版本升级。Go 1.22 与参考 Dockerfile 中的 Node 20 已超出官方支持周期，不能作为 2026-07 的新工程安全基线；Python 3.11 仍处于安全维护期。独立锁文件保护服务可独立构建与升级。

**Alternatives considered**:

- 继续 Go 1.22/Node 20：与“依赖必须受维护”的宪章要求冲突。
- 使用 Go 最新大版本或 Node Current：变化面更大；选择仍受支持的保守版本更适合首次骨架。
- Poetry 或 pnpm：能力足够，但单前端与三个独立 Python 服务没有足以抵消额外工具成本的收益。
- `requirements.txt` 或无锁 `npm install`：不能提供完整、可复现的传递依赖解析。

## 3. 根工作流架构与组件事实源

**Decision**: 根 `Makefile` 是唯一公开适配层，提供 `help` 和七个稳定公开入口 `dev`、`dev-down`、`fmt`、`lint`、`test`、`build`、`migrate`。稳定支撑入口包括 `bootstrap`、`type-check`、`toolchain-check`、`fmt-check`、`structure-check`、`contracts-check`、`migrate-check`、`migrate-integration-check`、`security-check`、`image-scan` 和 `ci`。`bootstrap` 在工具链验证后只执行锁定依赖准备，不安装系统工具或重写锁；`type-check` 可独立运行且仍由 `lint` 聚合。一个版本化组件清单持有八个边界的 owner、路径、工具链、允许依赖、测试根、交付物和动作绑定；Make 只编排清单并 fail-fast。

**Rationale**: 单一清单避免每个 Make target 与 CI 各维护组件列表。组件适配仍使用各语言原生工具，根入口通过 `$(MAKE) -C "<component>"` 或等价安全调用聚合。必需组件没有真实动作、没有测试或未初始化时必须失败。

**Alternatives considered**:

- 多处硬编码组件列表：极易漂移。
- 只保留组件 Makefile：开发者仍需记忆私有命令。
- 只检查目录存在：无法证明真实格式化、检查、测试或构建发生。

## 4. 最小组件骨架与运行契约

**Decision**: 建立 Go 网关、三个 Python 服务和 React 前端五个可部署骨架，但不实现任何业务路由。后端骨架只暴露 `GET /health/live`、`GET /health/ready`、`GET /metrics`；readiness 只证明自身初始化，不连接 SF02 的数据库、缓存或消息系统。未知业务路径返回 404。前端提供最小可访问页面、容器健康位置和安全构建信息。

每个后端服务都具有 request ID、脱敏结构化日志、真实健康/指标 smoke test；前端具有 strict TypeScript 与渲染 smoke test。`shared`、`infra`、`ops` 通过负向 fixture、契约/边界验证和确定性资产包提供真实 test/build 证据，不用空目录或 `.gitkeep` 伪装完成。

**Rationale**: 独立 liveness/readiness、指标和安全日志是宪章要求的可部署基线，不是业务占位。readiness 若探测未来依赖会越过 SF02 范围；提前创建完整 Clean Architecture 空树也没有可验证价值。

**Alternatives considered**:

- 单一 `/health`：无法区分存活与就绪。
- 创建 501 占位业务接口：会形成未经规格定义的公共契约。
- 创建空 `domain` 包：制造虚假的 80% 覆盖证据；领域代码出现后再启用 80% 门禁。
- 在 `shared/` 复制 Python/Go 运行时模型：违反单一版本化契约事实源原则。

## 5. 构建与容器

**Decision**: `make build` 构建五个多阶段、非 root、有健康检查的镜像，以及 `shared`、`infra`、`ops` 三个确定性资产包。镜像基础层固定补丁版本与 digest，标签只使用 `{semver}-{commit_sha}`，不生成 `latest`。每个服务拥有独立 build context 与 `.dockerignore`，不接收秘密型 build args，也不复制 `.env.*`。CI 构建后实际启动镜像、等待健康、执行 smoke，再扫描镜像。

**Rationale**: 仅成功执行 Docker build 或仅存在 `HEALTHCHECK` 都不能证明运行用户、健康端点或静态资源正确。独立上下文能阻止跨服务源码和秘密进入镜像。

**Alternatives considered**:

- 单个根上下文和动态服务参数：容易打破边界并复制无关文件。
- 单阶段或 root 镜像：增加攻击面并违反宪章。
- 浮动基础镜像或 `latest` 标签：不可复现、不可审计。

## 6. 工作流输出、退出与路径安全

**Decision**: 公开退出契约只承诺 `0=成功`、`非 0=失败`，因为 Make 会归一化子进程退出码。机器可判定原因使用稳定代码：`INVALID_USAGE`、`TOOL_MISSING`、`TOOL_VERSION_UNSUPPORTED`、`INVALID_CONFIG`、`INVALID_MODE`、`PROD_APPROVAL_REQUIRED`、`SF02_NOT_READY`、`COMPONENT_NOT_INITIALIZED`、`NO_TESTS_EXECUTED`、`STEP_FAILED`、`CONTRACT_DRIFT`、`MIGRATION_INVALID`、`SECRET_DETECTED`。

可解析输出采用 JSON Lines，每行至少包含 `schema_version`、`run_id`、`action`、`component`、`phase`、`status`、`code`、`duration_ms`、`message`。终端文本始终保留明确状态；颜色仅为可选增强并尊重 `NO_COLOR`。路径从 Makefile 自身位置解析，全部引用，不依赖固定绝对路径或对 `pwd` 的字符串拆分。

**Rationale**: 稳定错误码和 JSONL 同时满足自动化断言、人工诊断、中文路径及屏幕阅读器；输出只记录变量名和安全摘要，不记录秘密值。

**Alternatives considered**:

- 承诺精确数字退出码：经过 Make 后不稳定。
- 只输出自由文本或仅用颜色：难以解析且不可访问。
- 要求仓库路径不含空格/中文：直接违反 FR-022/SC-007。

## 7. 格式化与脏工作区

**Decision**: `make fmt` 只对声明范围原地运行格式化器，允许处理已修改源码，禁止 stash/reset/checkout/clean/delete；范围外文件与未跟踪文件必须保持内容和存在性，第二次执行零新增差异。`fmt-check` 使用各格式化器的 check/list 模式，不通过先修改整个 dirty worktree 再比较全局 Git diff 来判定。

**Rationale**: 这直接编码 clarification Q3，区分“格式化是明确修改”与“工作流不得破坏用户改动”。CI 在干净检出上可执行 `make fmt` 并验证无差异，日常本地检查使用非修改的 `fmt-check`。

**Alternatives considered**:

- 要求干净工作区：不必要地阻塞日常开发。
- 跳过 dirty 文件：导致同一目标在不同状态下结论不同。
- 自动 clean/reset：被规格明确禁止。

## 8. 环境模式与生产双门

**Decision**: 唯一语法是严格小写 `mode=local|test|prod`。未传时为 `local`；只有 Make 命令行来源的 `mode` 才能选择 `test` 或 `prod`，来自 shell、`.env`、文件名、`ENV`/`MODE` 的残留值不能升级环境。非法、空值或大小写变体必须在读取目标配置、DNS、网络或容器操作前失败。

生产操作需要两道独立门：显式 `mode=prod`，再加交互式精确确认短语，或非交互受保护环境提供的、绑定 action/commit/run 的审批证明。审批日志只记录引用，不记录 token。SF01 定义并测试此契约，不实施生产部署。

**Rationale**: `mode ?= local` 会接受环境注入，可能把残留变量静默升级到生产。双门满足澄清结果和受控发布原则。

**Alternatives considered**:

- 根据连接 URL、当前 shell 或文件名反推环境：不明确且危险。
- 只有 `[y/N]`：非交互场景不可审计。
- 仅凭分支名或 `mode=prod`：不构成额外审批。

## 9. SF02 过渡与迁移解耦

**Decision**: SF01 的 `dev`、`dev-down` 在检查 Docker、读取真实配置或访问资源前输出 `SF02_NOT_READY` 并失败，且不产生任何副作用；SF02 以后只替换内部 capability adapter，公开目标和输出契约不变。

迁移分为三层：`migrate-check` 离线验证 owner 清单、单 head、命名、upgrade/downgrade、顺序与回退文档；`migrate mode=...` 只连接外部已经提供且明确配置的目标，不隐式启动数据库；`migrate-integration-check` 使用固定 digest 的一次性 PostgreSQL 15 和合成凭证，按 API→Billing 执行 forward、backout、retry、最终 head 恢复，不调用 `make dev` 或共享数据库。CI 必须运行第三层而不能只验证 YAML/离线图。迁移 owner 顺序为 `api-service` 后 `billing-service`；`admin-service` 不拥有或直连其他服务数据库。零 pending migration 只有在真实图与 owner 校验完成后才可明确成功。

**Rationale**: 这避免 SF01 与 SF02 循环依赖，同时保留真实迁移证据和服务存储所有权。

**Alternatives considered**:

- `migrate` 隐式调用 `dev`：把迁移与本地编排强耦合。
- SF01 提前实现容器生命周期：侵入 SF02。
- 空脚本或未初始化 Alembic 报告成功：违反禁止空操作伪成功的决定。

## 10. CI 安全、扫描与恢复

**Decision**: 工作流顶层权限仅 `contents: read`，checkout 禁止持久化凭证；使用 `pull_request` 而非 `pull_request_target` 执行不受信任 PR。CI 无仓库/组织/环境秘密，只使用合成配置，不上传、不发布、不部署。

`make ci` 按顺序执行工具链检查、frozen bootstrap、格式漂移、独立 type-check、lint/边界、真实测试、契约漂移、离线迁移检查、隔离 PostgreSQL 15 迁移往返、Gitleaks 全历史秘密扫描、`govulncheck`、`pip-audit`、`npm audit`、五镜像构建与 smoke、Trivy HIGH/CRITICAL 镜像扫描。工具或漏洞数据库下载失败时失败关闭，仅允许一次有界幂等重试。例外必须有 ID、所有者、批准人、到期日和跟踪事项。

**Rationale**: 单一 `quality-gate` 易于 branch protection 配置并避免 job 名漂移。各生态原生扫描器提高语义准确性；固定版本/digest 降低第三方供应链风险。

**Alternatives considered**:

- 仅依赖托管平台 secret scanning/Dependabot：套餐与本地可复现性不确定。
- 第三方 scanner Actions：扩大 Action 权限与供应链面；核心扫描由 Make 调用固定 CLI。
- `continue-on-error` 或自动忽略无修复漏洞：不符合宪章阻断要求。
- 多 job 组件矩阵：初期会把组件事实源复制到 CI；实测出现瓶颈后再由清单生成矩阵。

## Sources

### Project authority

- [Engineering constitution](../../.specify/memory/constitution.md)
- [Feature specification](./spec.md)
- [Project architecture and workflow](../../项目开发/1-项目架构与目录结构.md)
- [Go gateway standard](../../项目开发/2-Go代理网关开发规范.md)
- [Python and database standard](../../项目开发/3-Python后端与数据库设计规范.md)
- [Frontend and DevOps standard](../../项目开发/4-前端与DevOps监控规范.md)

### Official external references

- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Actions dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [Node.js release lifecycle](https://nodejs.org/en/about/previous-releases)
- [Go release policy](https://go.dev/doc/devel/release)
- [Python supported versions](https://devguide.python.org/versions/)
- [Alembic migration drift check](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [Go vulnerability checking](https://go.dev/doc/tutorial/govulncheck)
- [npm clean install](https://docs.npmjs.com/cli/commands/npm-ci/)
- [Trivy vulnerability scanner](https://trivy.dev/docs/latest/scanner/vulnerability/)
