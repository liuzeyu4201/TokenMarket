# 工作流运行手册（runbook）

## 长期分支

| 分支 | 角色 | 典型合入路径 |
|--------|------|--------------------|
| `master` | **生产分支** — 始终可发布；生产部署的代码源 | 经评审的 PR 从 `master-dev` 或 hotfix 合入 `master` |
| `master-dev` | **测试环境部署分支** — 集成与预生产验证 | 功能 / 修复 PR 合入 `master-dev` |

这两个名称固定。不得重命名，也不得在未评审契约变更的情况下
发明额外的长期部署线。

## 分支命名标准

所有短期分支使用**小写 ASCII**、**kebab-case**，且**无空格**。
分支名不得编码环境（`local` / `test` / `prod`）；环境始终通过显式
`mode=` 选择（见下文）。

### 语法

```text
long-lived   := master | master-dev
spec-feature := <NNN>-<slug>                 # only when specs/NNN-slug/ exists
other        := <kind>/<slug>
kind         := feat | fix | hotfix | docs | chore | refactor
slug         := [a-z0-9]+(-[a-z0-9]+)*     # English words, hyphens only
NNN          := [0-9]{3}                     # zero-padded Spec Kit feature id
```

推荐总长：**≤ 50 字符**。避免下划线、点号（除规范不允许的以外）、
大写、中文或其他非 ASCII、人名，以及无 slug 的裸工单号
（例如优先 `fix/gateway-request-id`，而不是单独的 `fix/1234`）。

### 功能分支（主路径）

当工作在（或将有）`specs/` 下的 Spec Kit 功能时：

| 规则 | 要求 |
|------|-------------|
| 名称形式 | `NNN-short-kebab-description` |
| 身份 | 分支基名**必须**与 `specs/` 下功能目录名一致 |
| 基线分支 | 从当前健康的 `master-dev` 创建 |
| PR 目标 | `master-dev` |
| 示例 | `001-repository-workflow-baseline`、`002-local-dependency-lifecycle` |

按升序分配 `NNN`（下一个空闲的三位 id）。不得把同一 id 复用于不同功能。
不得发明仅前缀不同的平行名称（已有编号 Spec Kit 功能时，禁止
`feature/002-...` 或 `feat/002-...`）。
在没有匹配的 `specs/NNN-.../` 目录时，**不得**发明 `NNN-...` 分支名。

### 其他短期分支

当变更**不是**作为 `specs/` 下 Spec Kit 功能跟踪，或为紧急生产修复时使用：

| 前缀 | 使用场景 | 从何处拉出 | PR 合入 |
|--------|----------|-----------|---------|
| `feat/<slug>` | **无** Spec Kit `specs/NNN-...` 功能的产品/行为变更 | `master-dev` | `master-dev` |
| `fix/<slug>` | 测试线缺陷修复 | `master-dev` | `master-dev` |
| `hotfix/<slug>` | 紧急生产修复 | `master` | `master`，然后**回合并**到 `master-dev` |
| `docs/<slug>` | 仅文档 | `master-dev` | `master-dev` |
| `chore/<slug>` | 工具链、依赖、CI 管线，无产品行为 | `master-dev` | `master-dev` |
| `refactor/<slug>` | 内部重构，无预期行为变化 | `master-dev` | `master-dev` |

示例：`feat/layered-compose-deploy`、`fix/api-readiness-timeout`、
`hotfix/migrate-approval-bypass`、`docs/local-environment-runbook`、
`chore/uv-lock-refresh`。

### 禁止

- 环境或部署线名称：把 `test`、`prod`、`local`、`staging`、`dev` 当作
  完整分支名（或伪长期线）。
- 替代长期线：`main`、`develop`、`release/*`（除非未来契约替换本标准）。
- Spec 功能与分支名不匹配：跟踪为 `specs/004-foo/` 的工作**必须**使用
  分支 `004-foo`，而不是 `feat/foo`、`feature/foo` 或 `004_foo`。
- 与现有 `specs/NNN-.../` 目录不匹配的编号 `NNN-...` 分支。
- 在分支名中编码密钥、主机名或客户数据。

### 开发流程

1. 从 `master-dev` 拉出分支（仅 `hotfix/*` 从 `master` 拉出）。
2. 按上表目标开 PR；`quality-gate` 必须通过。
3. 测试环境验证后，从 `master-dev` 向 `master` 开晋升 PR。
4. 合入 `master` 的 hotfix **必须**回合并到 `master-dev`。

`make migrate` 与 `make deploy` / `make deploy-down` 的环境选择**不**
从分支推断。按 `shared/contracts/repository-workflow/v1/environment-mode.md`
使用显式 `mode=local|test|prod`（`prod` 需生产审批）。未来 CD 作业可
从 `master-dev` / `master` *调度*，但仍须在命令行传入显式 `mode=`。

### 分层 Compose（ADR 003）

| 命令 | 环境 | 运行内容 |
|---------|-------------|-----------|
| `make dev` / `make dev-down` | 仅 local | 中间件容器；应用保持主机进程 |
| `make build` | 任意 | 五个服务镜像 + 资产包 |
| `make deploy` / `make deploy-down` | 仅 test 或 prod | 共享主机上的中间件 + 应用容器 |
| `make migrate` | local / test / prod | 仅已评审 Alembic；永不启动容器 |

本地日常默认入口为 `make start` / `make stop`（中间件 + 五个主机应用进程）。
中间件单独操作继续使用已激活的 `make dev` / `make dev-down`。
`make deploy` / `make deploy-down` 在部署适配器落地前保持失败关闭（fail-closed）。

见 [`deploy.md`](deploy.md) 与 `docs/decisions/003-layered-compose-deploy.md`。

## 本地配置

1. 将 `.env.example` 复制为 `.env.local`。
2. 用本地合成值替换占位符。
3. 切勿提交 `.env.local` 或任何含真实凭据的文件。

## 密钥发现

若在 Git 历史或构建输出中发现真实密钥：

1. 立即吊销/轮换该凭据。
2. 通过提供商日志审计使用情况。
3. 开可跟踪的修复工单，写明负责人、审批人与到期日。
4. 仅在审计之后，才考虑经批准的最小化历史修复。

### 例外记录格式

每条安全例外必须记录：

| 字段 | 示例 |
|-------|---------|
| Owner | security-oncall@tokenmarket.local |
| Approver | eng-lead@tokenmarket.local |
| Issue | PROJ-1234 |
| Expiry | 2026-08-15 |
| Reason | transient allow-list for integration test fixture |

例外不能替代轮换；必须有固定到期日，续期前须再评审。

## CI 恢复

- 回滚期间保持必需作业名 `quality-gate` 稳定。
- 怀疑缓存污染：提升 cache key 或禁用缓存。
- `master` 或 `master-dev` 合并失败：开评审后的 revert PR；切勿 force-push。

### Runner 或扫描器失败

若 `quality-gate` 因托管工具或扫描器不可用而失败：

1. 在 `ops/workflow/toolchains.json` 中核对固定版本/SHA。
2. 用 `make ci` 确认本地可复现。
3. 若仅 runner 缺少扫描器，通过 CI workflow 以相同固定引用安装；
   不得降级或跳过该步骤。
4. 在本运行手册中记录事件与处理结果。

### 必需检查的上线顺序

1. 合入 CI workflow，并验证至少一次成功的 PR `quality-gate` 运行。
2. 在 `master` 与 `master-dev` 的分支保护/ruleset 中启用
   `quality-gate` 必需状态检查。
3. 对每个 ruleset 启用 “Do not allow bypassing the above settings”。
4. 启用 “Restrict pushes that create files” 与 “Require a pull request before merging”。

### GitHub ruleset 配置

为长期分支配置仓库 ruleset：

#### `master`（生产）

- **Target branches**：`master`
- **Bypass list**：空（任何角色、团队或应用均不可绕过）
- **Restrictions**：禁止直接 push 与 force push
- **Pull request**：必需，至少 1 名评审人，新提交时使过期审批失效
- **Required status checks**：`quality-gate`
- **Commit message**：除非后续 ADR 采纳，否则不要求签名提交
- **Promotion**：优先在测试验证后合入 `master-dev` → `master` 的 PR

#### `master-dev`（测试部署）

- **Target branches**：`master-dev`
- **Bypass list**：空
- **Restrictions**：禁止直接 push 与 force push
- **Pull request**：必需，至少 1 名评审人，新提交时使过期审批失效
- **Required status checks**：`quality-gate`

### 关联 PR 与最终长期分支运行

每个 PR 在合入前必须有绿色 `quality-gate` 运行。合入后，`master` 或
`master-dev` 上的 `push` 触发为该 tip 产生最终运行。
事件响应与发布验收证据须同时引用 PR 运行 ID 与最终长期分支运行 ID
（生产环境还须引用晋升到 `master` 的 PR）。
