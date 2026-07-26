# Quickstart Validation: 仓库工程工作流基线

**Feature**: `001-repository-workflow-baseline`

**Purpose**: 实现后的可运行验收指南；不替代自动化测试

**Safety**: 不得使用真实凭据或生产配置

## 1. Prerequisites

使用全新检出或可丢弃的工作副本。必需版本与完整性引用由仓库工具链文件负责；应校验，而非依赖已预装内容。

```bash
make help
make toolchain-check
make bootstrap
```

Expected:

- `make help` 在 2 秒内完成，并列出 `dev`、`dev-down`、`fmt`、`lint`、`test`、`build`、`migrate` 及其前置条件、副作用与恢复说明。
- `toolchain-check` 报告受支持的 Make、Go、Python/uv、Node/npm、Docker 与扫描器版本，不安装或升级它们。
- `bootstrap` 仅准备锁解析的仓库工具、Go、Python 服务与前端依赖；不安装系统工具或重写任何锁文件，且第二次运行解析出相同依赖图。
- 缺失或不支持的工具在任何持久副作用前 5 秒内失败。

命令契约见 [`contracts/make-workflow.md`](./contracts/make-workflow.md)。

## 2. Prepare synthetic local configuration

```bash
cp .env.example .env.local
git status --short
```

Expected:

- `.env.local` 被忽略且不出现在 status 中。
- `.env.example` 仅包含名称、注释与不可用的占位符。
- 无命令打印配置值。

SF01 验收时不得将占位符替换为提供商密钥或生产值。

## 3. Validate successful root and supporting actions

```bash
make fmt
make fmt-check
make type-check
make lint
make test
make build
```

Expected:

- 全部八个必需组件运行真实适配器；无一被静默跳过。
- Go gateway、三个 Python 服务与前端各自执行真实冒烟测试。
- `shared`、`infra` 与 `ops` 各自执行负向 fixture 测试并创建确定性资产归档。
- 五个不可变服务镜像以 version/SHA 标签构建；不创建 `latest` 标签。
- 第二次 `make fmt` 不产生新差异。
- 必需组件若发现零测试或空动作适配器，聚合必须失败。

自动化测试覆盖注入的组件失败；不要删除真实组件来手动测试此项。

## 4. Validate dirty-worktree formatting safety

通过公共测试目标运行专用于脏工作树的仓库工作流测试：

```bash
make test
```

该 fixture 创建包含已跟踪编辑、超出范围文件与未跟踪文件的可丢弃仓库副本。它证明 `make fmt`：

- 仅格式化已声明文件；
- 永不运行 reset、checkout、stash、clean 或 delete；
- 保留超出范围与未跟踪内容；
- 第二次运行产生零额外差异。

权威行为定义于 [`contracts/make-workflow.md`](./contracts/make-workflow.md)。

## 5. Validate SF02 transition behavior

在 SF02 实现前，分别运行各目标并期望非零结果：

```bash
make dev
make dev-down
```

Expected for both:

- 诊断码为 `SF02_NOT_READY`。
- 输出说明 SF02 必须提供生命周期适配器。
- 不检查或不调用 Docker。
- 不读取任何配置文件。
- 不创建、停止、移除或更改任何容器、卷、网络或工作树文件。

此预期失败是通过 SF01 验收的条件。SF02 之后，本节由 SF02 的生命周期 quickstart 取代，同时公共目标名称保持不变。

## 6. Validate environment-mode safety

语法与审批规则见 [`contracts/environment-mode.md`](./contracts/environment-mode.md)。

### Invalid mode

```bash
make migrate mode=PROD
```

Expected: 在任何配置、DNS 或网络访问前返回非零 `INVALID_MODE`。

### Omitted mode

```bash
make migrate
```

Expected: 有效模式为 `local`。若外部无可用本地数据库，命令以缺失的本地配置/依赖名称安全失败；它永不启动数据库或回退到 test/production。

### Shell-origin escalation

```bash
mode=prod make migrate
```

Expected: shell 来源不能选择生产；动作保持 local，或在来源模糊时安全失败。

### Production without approval

```bash
make migrate mode=prod
```

Expected: 在生产配置或资源访问前返回 `PROD_APPROVAL_REQUIRED`。本指南有意不提供生产确认短语或审批证明。

永不使用真实生产 URL 测试这些预检用例。

## 7. Validate migration ownership and round-trip

```bash
make migrate-check
make migrate-integration-check
```

Expected:

- 负责人恰好为 `api-service` 然后 `billing-service`；`admin-service` 被明确为非负责人。
- 每个已初始化迁移图有一个 head 与有效的 upgrade/downgrade 元数据。
- 仅在图与负责人校验之后，才显式报告零待处理修订。
- 命令不执行任何网络操作。

`migrate-integration-check` 是独立集成层：它仅启动带合成凭据的固定 digest PostgreSQL 15 容器，按 API 然后 Billing 运行前向迁移、回退、重试与最终 head 恢复，然后丢弃 fixture。它永不调用 `make dev` 或接触共享数据库。

`make ci` 必须调用两个迁移检查，且不能用 YAML 或离线校验替代集成层。

## 8. Validate path and terminal accessibility

```bash
NO_COLOR=1 make help
make test
```

Expected:

- 无颜色或图标时纯文本状态仍完整。
- 工作流 fixture 测试从同时含空格与中文字符的可丢弃路径运行仓库。
- 事件中的路径为仓库相对路径，且不访问 fixture 外同名目录。
- JSON Lines 事件对照 [`contracts/workflow-event.schema.json`](./contracts/workflow-event.schema.json) 校验通过。

## 9. Validate security gates

```bash
make security-check
```

Expected:

- 全历史密钥扫描对仓库通过，并检测到合成正向 fixture。
- Go、全部 Python 锁与 npm 锁被扫描且不修改锁文件。
- 扫描器/数据库下载失败在至多一次有界重试后仍为失败门禁。
- 输出对 fixture 值脱敏。

`make build` 之后：

```bash
make image-scan
```

Expected: 全部五个不可变镜像扫描 HIGH/CRITICAL 发现；例外仅在包含必需 ID、分析、负责人、审批、issue 与到期时间时被接受。

## 10. Run the complete local CI gate

```bash
make ci
```

Expected:

- 顺序匹配 [`contracts/ci-gates.md`](./contracts/ci-gates.md)。
- 仅当每个阻塞步骤产生证据时，最终事件为 `PASSED`。
- 在同一提交上重跑产生相同结果且无意外已跟踪差异。
- 不发布或部署任何服务。

## 11. Verify hosted CI

实现后打开或更新针对 `master-dev` 的 pull request（仅在测试验证后晋升到 `master`）。

Expected:

- 恰好一个稳定必需检查 `quality-gate` 运行，无路径过滤。
- 工作流以 `make ci` 作为其唯一项目命令调用。
- 可丢弃测试分支上的故意失败 fixture 阻止合并。
- 成功合并对最终 `master-dev` 或 `master` 提交触发同一门禁。
- 工作流 token 权限只读，且无可用仓库/生产密钥。

## 12. Evidence to attach to review

- `make help` 与 `toolchain-check` 输出。
- 组件测试计数与覆盖率摘要。
- 契约、边界与 migration-check 结果。
- 五个不可变镜像引用加运行时健康冒烟结果。
- 密钥/依赖/镜像扫描摘要，敏感值已脱敏。
- PR 与最终 `master-dev` / `master` 提交的 `quality-gate` URL/结果。
- 确认未引入业务 schema、提供商凭据、生产资源或部署。
