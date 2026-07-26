# Data Model: 仓库工程工作流基线

**Feature**: `001-repository-workflow-baseline`

**Date**: 2026-07-13

**Persistence model**: 版本控制的工程元数据加临时运行证据；无业务数据库表

## Overview

本功能对仓库工作流事实建模，而非 TokenMarket 业务数据。持久定义存放于版本控制，并对照 [`contracts/`](./contracts/) 中的 schema 校验。运行时命令事件与 CI 证据为临时输出，由本地终端或 CI 平台保留。

```text
ComponentBoundary 1 ── * ComponentActionBinding * ── 1 WorkflowCommandDefinition
        │                              │
        ├── * ToolchainRequirement     └── * WorkflowStepResult
        └── * SharedContractArtifact             │
                                                  *
EnvironmentSelection 1 ── 0..1 ProductionApproval   WorkflowRun
        │
        └── 0..* MigrationPlan ── 1 MigrationOwner

CIGate * ── 1 WorkflowCommandDefinition
```

## Entity: WorkflowCommandDefinition

表示一个公共或支持性的根工作流动作。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `name` | string | 唯一，小写 kebab-case；公共名称为 `help`、`dev`、`dev-down`、`fmt`、`lint`、`test`、`build`、`migrate`；稳定支持名称包括 `bootstrap`、`type-check`、`migrate-integration-check` |
| `visibility` | enum | `public` 或 `supporting` |
| `purpose` | string | 非空，对 help 输出安全 |
| `preconditions` | list | 副作用前按序运行的检查 |
| `ordered_steps` | list | 引用组件动作或工作流检查 |
| `side_effect_class` | enum | `none`、`workspace-format`、`local-resource`、`persistent-data`、`artifact-build` |
| `mode_policy` | enum | `not-applicable`、`optional-default-local`、`required` |
| `success_semantics` | string | 必须定义可观察证据，永不仅“命令已返回” |
| `failure_codes` | list | 工作流事件契约允许的值 |
| `recovery` | string | 安全重试/回退说明 |
| `output_contract_version` | string | 工作流事件 schema 的语义版本 |

**Invariants**:

- 每个公共命令恰好出现一次；稳定的 `bootstrap` 与 `type-check` 支持命令也恰好出现一次。
- `bootstrap` 先校验系统工具，使用已提交锁，永不安装系统工具且永不重写锁文件。
- 有副作用的命令在第一个有副作用步骤前列出前置条件。
- 必需步骤不能有空适配器或空证据规则。
- `dev` 与 `dev-down` 在能力为 `blocked_on_sf02` 时仍保持公共。
- 精确的非零退出码数值不属于公共契约。

**Owner/source of truth**: 仓库维护者；根 Make 工作流与命令契约。

**Classification/retention**: 公共工程元数据；保留于 Git 历史。

**Audit**: 语义变更要求在同一经评审变更中更新规格/契约/CI。

## Entity: ComponentBoundary

表示一个必需的所有权边界。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `id` | enum | `proxy-gateway`、`api-service`、`billing-service`、`admin-service`、`frontend`、`shared`、`infra`、`ops` |
| `path` | repository-relative path | 唯一；必须解析到仓库根内 |
| `owner` | string | 非空团队或维护者角色 |
| `responsibility` | string | 不得复制另一组件的领域所有权 |
| `component_type` | enum | `go-service`、`python-service`、`web-frontend`、`contract-assets`、`infrastructure-assets`、`operations-assets` |
| `allowed_dependencies` | list of component IDs | 有向白名单；禁止自引用 |
| `test_root` | path | 必须存在于组件路径内且包含可发现测试 |
| `deliverable_type` | enum/list | 二进制、容器镜像、静态站点镜像、确定性资产归档 |
| `required` | boolean | 对 SF01 的八个边界始终为 `true` |
| `lifecycle_state` | enum | `declared`、`scaffolded`、`verified` |

**Invariants**:

- 路径唯一性区分大小写，符号链接解析不得逃出仓库根。
- 服务不能导入另一服务的内部包或读取其持久化存储。
- `shared` 存储版本化契约与生成元数据，而非复制的服务业务逻辑。
- `admin-service` 在 SF01 中无迁移所有权，且不能访问 API/billing 存储。
- `verified` 要求所有强制动作绑定产生证据。

**State transition**:

```text
declared ── structure created ──> scaffolded ── fmt/lint/test/build pass ──> verified
   ^                                  │
   └──── missing/invalid structure ───┴──── contract or action failure ───> failed run
```

**Owner/source of truth**: 由 `component-manifest.schema.json` 校验的组件清单。

**Classification/retention**: 公共工程元数据；Git 保留。

**Reconciliation**: `structure-check` 比较清单、仓库路径、Make 适配器与测试。

## Entity: ComponentActionBinding

将组件连接到工作流动作。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `component_id` | ComponentBoundary ID | 必需 |
| `action` | enum | `bootstrap`、`fmt`、`fmt-check`、`type-check`、`lint`、`test`、`build`，可选 `migrate` |
| `adapter` | path/target reference | 必须解析到组件内且非空 |
| `required` | boolean | 强制绑定不可跳过 |
| `evidence_type` | enum | `formatted-files`、`static-report`、`test-count`、`coverage-report`、`image`、`asset-archive`、`migration-result` |
| `minimum_evidence` | object | 对测试动作包含 `executed_tests >= 1` |
| `timeout_seconds` | positive integer | 每动作有界；精确值在 tasks/config 中最终确定 |

**Identity**: `(component_id, action)` 唯一。

**Failure rule**: 必需绑定失败则运行失败；后续必需绑定变为带安全原因的 `SKIPPED`，永不 `PASSED`。

## Entity: ToolchainRequirement

表示受支持的工具或扫描器及其版本来源。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `tool` | string | 范围内唯一 |
| `exact_version` | string | CI/扫描器必需；语言兼容性也可声明范围 |
| `version_source` | path | 拥有该值的仓库文件或锁文件 |
| `affected_components` | component IDs | 非空 |
| `install_policy` | enum | `preinstalled-required`、`locked-package-manager`、`verified-download`、`pinned-container` |
| `integrity_reference` | checksum/digest/SHA | 下载的二进制、容器与 Actions 必需 |
| `execution_overrides` | 可选 object | 工具链执行配置文件（execution profile）id → override 对象的映射。每个 override 要求 `match: exact-list` 与非空 `allowed_versions` 字符串列表（仅精确成员匹配）。可选 `rationale` 仅作说明 |

**执行配置文件（execution profile）**（`toolchain-check` 的输入，不是 Make 的 `mode`）：

| Profile id | 选择方式 | 版本解释 |
|------------|-----------|------------------------|
| `local`（默认） | 显式 `--toolchain-profile`，否则 `TOKENMARKET_TOOLCHAIN_PROFILE`，再否则默认 | 使用 `exact_version` 与既有匹配规则 |
| `github-actions-ubuntu-24.04` | 必须显式；永不从 `CI`/`GITHUB_ACTIONS` 推断 | 对有对应 override 的工具使用 exact-list 批准列表；要求 `GITHUB_ACTIONS=true` 与 `RUNNER_OS=Linux` |

**Invariants**:

- 本地与 CI 检查读取同一版本来源文件（`ops/workflow/toolchains.json`）；解释可仅因显式 execution profile 而不同。
- 缺失或不支持的版本在组件动作前失败。
- 未知 profile、空批准列表、未知 `match` 值与托管真实性检查失败均失败关闭。
- 工作流命令永不静默安装或升级工具链。
- 缓存命中永不替代版本或完整性校验。
- SF02 本地依赖生命周期的 Docker/Compose 精确钉选独立于本实体的托管 overrides。

## Entity: ConfigurationDefinition

描述配置名称，不包含真实值。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `name` | uppercase identifier | 唯一 |
| `value_type` | enum | `string`、`integer`、`boolean`、`url`、`duration`、`enum` |
| `required_modes` | set | `local`、`test`、`prod` 的子集 |
| `sensitivity` | enum | `public`、`internal`、`secret`、`personal`、`financial` |
| `safe_placeholder` | string | 必须为合成且不可用；密钥占位符不能匹配提供商凭据格式 |
| `description` | string | 非空且对公共文档安全 |
| `owner_component` | component ID | 必需 |

**Invariants**:

- 定义或已提交示例中不存储真实值。
- 日志与校验错误提及 `name`，永不提及所提供的值。
- 除安全 `*.example` 文件外，`.env`、`.env.*` 被忽略。
- 生产必需的安全/持久化值无可用默认值。

## Entity: EnvironmentSelection

表示迁移与未来部署命令的环境选择。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `mode` | enum | 精确小写 `local`、`test`、`prod` |
| `input_origin` | enum | `make-command-line`、`omitted`、`shell-environment`、`file`、`legacy-variable` |
| `effective_mode` | enum | 省略变为 `local`；仅命令行输入可选择 `test` 或 `prod` |
| `config_reference` | path/reference | 仅在模式校验后选择；真实文件仍被忽略 |
| `approval_required` | boolean | 仅对 `prod` 为 `true` |
| `preflight_state` | enum | `requested`、`validated`、`approved`、`connection_allowed`、`rejected` |

**State transitions**:

```text
omitted/requested ──> validated(local) ──> connection_allowed
explicit test      ──> validated(test)  ──> connection_allowed
explicit prod      ──> validated(prod)  ──> approved ──> connection_allowed
invalid/source escalation/approval missing ─────────────> rejected
```

**Critical invariant**: `rejected` 发生在读取目标配置、解析目标 DNS、启动容器或打开网络连接之前。

## Entity: ProductionApproval

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `approval_type` | enum | `interactive-phrase`、`protected-environment` |
| `action` | string | 必须等于请求的动作 |
| `commit_sha` | string | 非交互审批必需 |
| `run_id` | string | 非交互审批必需 |
| `approval_reference` | string | 安全审计引用；永不作为 token |
| `approved_at` | timestamp | UTC |

审批为临时且对其绑定的动作/提交/运行一次性有效。审批 token 或评审者凭据永不由工作流模型记录或存储。

## Entity: MigrationOwner

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `component_id` | enum | SF01 中为 `api-service` 或 `billing-service` |
| `order` | integer | 唯一；API 先于 billing |
| `version_path` | repository-relative path | 必须保持在负责人组件内 |
| `expected_heads` | positive integer | 初始化后恰好 `1` |
| `owns_database` | boolean | 必须为 true |
| `backout_runbook` | path | 必需且链接有效 |

`admin-service` 被明确不为迁移负责人。禁止跨负责人外键与直接存储访问。

## Entity: MigrationPlan

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `owner` | MigrationOwner | 必需 |
| `mode` | EnvironmentSelection | apply 必需；离线检查不需要 |
| `current_head` | revision ID or `base` | 派生 |
| `target_head` | revision ID or `base` | 派生 |
| `pending_count` | non-negative integer | 仅在已初始化图校验后允许为零 |
| `forward_evidence` | reference | 变更的迁移必需 |
| `backout_evidence` | reference | 变更的迁移必需 |
| `retry_evidence` | reference | 变更的迁移必需 |

SF01 不创建业务表。CI 迁移证据使用隔离 PostgreSQL 15 实例与合成凭据。

## Entity: WorkflowRun

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `run_id` | UUID/opaque unique ID | 每次调用唯一 |
| `action` | command name | 必需 |
| `mode` | effective mode or null | 不适用时为 null |
| `started_at` | timestamp | UTC |
| `completed_at` | timestamp or null | 在终态时设置 |
| `status` | enum | `PENDING`、`RUNNING`、`PASSED`、`FAILED` |
| `step_results` | ordered list | 非 help 动作至少一个 |

**State transition**: `PENDING → RUNNING → PASSED|FAILED`；终态不可变。

**Retention/classification**: 临时运维证据，无密钥或个人数据。本地输出不提交；CI 日志/工件遵循实现期间定义的仓库保留设置。

## Entity: WorkflowStepResult

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `schema_version` | semantic version | 必需 |
| `run_id` | WorkflowRun ID | 必需 |
| `action` | string | 必需 |
| `component` | component ID or `repository` | 必需 |
| `phase` | string | 稳定短标识符 |
| `status` | enum | `STARTED`、`PASSED`、`FAILED`、`SKIPPED` |
| `code` | stable error/status code | 失败/跳过时必需；否则为安全成功码 |
| `duration_ms` | non-negative integer | 终态步骤事件必需 |
| `message` | string | 人类可读、脱敏的安全摘要 |

## Entity: CIGate

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `id` | string | 唯一；必需作业为 `quality-gate` |
| `triggers` | set | 针对 `master` 与 `master-dev` 的 PR/push、手动；启用时含 merge group |
| `root_target` | string | `ci` |
| `blocking` | boolean | 对必需门禁始终为 true |
| `permissions` | map | `contents: read`；所有未指定权限为 none |
| `evidence` | list | 冻结 bootstrap、format、独立 type-check、lint/边界、测试、契约、离线加隔离 PostgreSQL 迁移、密钥/依赖/镜像、构建/冒烟 |
| `retention_policy` | reference | CI 设置；必须排除密钥 |

**Invariants**:

- CI 项目逻辑仅调用根工作流目标。
- 不允许生产部署、发布或含密钥动作。
- 失败的必需步骤不能使用 `continue-on-error`。
- 必需作业名在回滚过程中保持稳定。

## Entity: SharedContractArtifact

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `contract_id` | string | 唯一 |
| `owner` | component/maintainer | 必需 |
| `version` | semantic version | 必需 |
| `format` | enum | JSON Schema、OpenAPI、事件 schema、Markdown 开发者契约 |
| `compatibility` | enum | `backward-compatible`、`breaking-new-version` |
| `deprecated_at` | date or null | 仅在弃用时必需 |
| `replacement` | contract reference or null | 弃用时必需 |

生成的消费者是契约源的可复现输出，而非独立事实。契约漂移使 CI 失败。
