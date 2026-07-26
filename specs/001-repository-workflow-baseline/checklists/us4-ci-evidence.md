# US4 证据：本地/CI 一致性

**故事**：User Story 4 — 在本地与持续集成中获得相同结论
**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14
**提交**：实现中的仓库状态（设计基线未变）

## 范围

本证据记录：仓库根工作流在本地与 GitHub Actions 薄适配器中
产生相同的步骤序列；`mode` 选择
不得被隐式升级；脏工作树与特殊路径得到
安全处理；且 CI 门禁在任一必需步骤上 fail-closed。

## T083–T089：契约测试

| 测试文件 | 结果 |
|-----------|--------|
| `tests/workflow/test_paths.py` | 2/2 通过 |
| `tests/workflow/test_dirty_format.py` | 2/2 通过 |
| `tests/workflow/test_mode.py` | 7/7 通过 |
| `tests/workflow/test_retry_safety.py` | 1/1 通过 |
| `tests/workflow/test_accessibility_performance.py` | 3/3 通过 |
| `tests/workflow/test_ci_contract.py` | 4/4 通过 |
| `tests/workflow/test_reproducibility.py` | 2/2 通过 |

完整 `tests/workflow` 回归：**185 通过**。

## T090–T096：实现

### 模式强制（`tools/workflow/mode.py`）

- `validate_mode` 对 `test`/`prod` 接受 `command` 与 `command line` 来源。
- 来自不安全来源的 `environment`、`file`、`shell`、`override` 被拒绝。
- `prod` 需要通过交互短语或 `approval_proof` 的显式批准。

### 根工作流（`Makefile` / `tools/workflow/cli.py`）

新的公共目标：

```text
make ci
```

根 `Makefile` 中定义的固定顺序：

```text
toolchain-check → bootstrap → fmt-check → type-check → lint → test →
migrate-check → migrate-integration-check → security-check → build →
runtime-smoke → image-scan
```

`runtime-smoke` 与 `image-scan` 在 `tools/workflow/images.py` 中实现，
并通过 `workflow.cli` 暴露。

### GitHub Actions 薄适配器（`.github/workflows/ci.yml`）

- 作业名：`quality-gate`
- 运行器：`ubuntu-24.04`
- 触发：向 `master` / `master-dev` 的 `push`、`pull_request`、`merge_group`、`workflow_dispatch`
- 权限：`contents: read`
- 检出：固定 `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`，带
  `fetch-depth: 0` 与 `persist-credentials: false`
- Setup actions 以完整 SHA 固定：
  - `actions/setup-go@f111f3307d8850f501ac008e886eec1fd1932a34`
  - `actions/setup-node@cdca7365b2dadb8aad0a33bc7601856ffabcc48e`
  - `astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86`
- 唯一项目命令：`make ci`
- 无路径过滤、密钥、发布或写权限。

### 组件 `fmt-check`

全部八个组件均暴露非变更的 `fmt-check` 目标：

- `services/proxy-gateway/Makefile`
- `services/api-service/Makefile`
- `services/billing-service/Makefile`
- `services/admin-service/Makefile`
- `frontend/Makefile`
- `shared/Makefile`
- `infra/Makefile`
- `ops/Makefile`

## 本地 `make ci` 运行

执行的命令：

```bash
PATH="/Users/token/.local/go1.25.12/bin:/Users/token/.local/bin:/Users/token/go/bin:/Users/token/.nvm/versions/node/v24.18.0/bin:$PATH" make ci
```

结果：

| 步骤 | 结果 |
|------|--------|
| `toolchain-check` | PASSED |
| `bootstrap` | PASSED |
| `fmt-check` | PASSED (9/9) |
| `type-check` | PASSED (9/9) |
| `lint` | PASSED (9/9) |
| `test` | PASSED (9/9) |
| `migrate-check` | PASSED |
| `migrate-integration-check` | PASSED (PG15 forward/backout/retry) |
| `security-check` | **FAILED** — pip-audit 报告已知 `starlette 0.45.3` 漏洞 |
| `build` | PASSED (9/9) |
| `runtime-smoke` | PASSED（5/5 镜像健康，非 root） |
| `image-scan` | **FAILED** — 本地未安装 Trivy 0.61.0 |

退出码：`2`（security-check fail-closed）

`security-check` 失败是对已在 `us2-security-evidence.md` 中记录的
已知 `starlette 0.45.3` 发现的预期 fail-closed 行为。
`image-scan` 失败是环境性的（本地工作站未安装 Trivy）；
CLI 返回 `TOOL_MISSING` 并 fail-closed，而非静默跳过扫描。

## 模式矩阵

| 命令 | 预期 | 已验证 |
|---------|----------|----------|
| `make migrate` | 默认 mode=local | PASSED |
| `mode=test make migrate` | 接受（command 来源） | PASSED |
| `mode=prod make migrate` | 在资源访问前拒绝（无批准） | PASSED |
| `MODE=test make migrate` | 拒绝（environment 来源） | PASSED |

## 脏工作树 / 特殊路径说明

- `make fmt` 仅触碰已声明的源文件；`.gitignore` 保留未跟踪文件。
- 根解析使用工作流脚本位置，因此仓库可检出到
  含空格或非 ASCII 字符的路径下。
- 重试安全：非 `fmt` 动作不变更工作树；`fmt` 幂等性
  由组件格式化器验证。

## 托管门禁变绿的已知阻塞

1. **Trivy 安装** — `image-scan` 需要运行器上的 Trivy 0.61.0。
2. **starlette 漏洞** — `security-check` 需要经评审的依赖
   更新或明确的、带过期时间的例外，门禁才能通过。

两者均作为 fail-closed 结果跟踪，而非 CI 适配器缺陷。

## T097：入门路径

见 `specs/001-repository-workflow-baseline/quickstart.md` 与更新后的
`README.md`（Phase 7），了解从检出到首次 `make ci` 的路径。

## T098/T099：运行手册与规则集

记录于 `ops/runbooks/workflow.md`：

- CI 缓存污染恢复。
- 运行器/扫描器失败处理。
- 失败的 `master` / `master-dev` 评审-回退流程。
- 必需检查的上线顺序。
- 针对 `quality-gate`、`master` / `master-dev` 保护与绕过防护的
  GitHub 规则集配置。
- 关联 PR 与最终 `master` / `master-dev` 的 `quality-gate` 运行。
