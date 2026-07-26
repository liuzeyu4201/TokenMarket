# ADR 004: 托管工具链执行 Profile

**Status**: Accepted
**Date**: 2026-07-26
**Owner**: TokenMarket Engineering
**Deciders**: Repository maintainers / Platform team
**Related**: ADR 001（GitHub Actions CI 适配器）、ADR 002（本地 Compose 生命周期）

## 背景

仓库级 `make toolchain-check` 从 `ops/workflow/toolchains.json` 读取维护中的 Docker 版本 `29.5.3`（本地通过现有 `_version_matches` 接受 `29.5.*`）。GitHub 托管的 `ubuntu-24.04` runner 预装 Docker CLI 为 `28.0.4`，且 workflow 故意不安装另一套 Docker Engine。

结果是：在未区分执行环境时，`quality-gate` 的 Integrity scan 在 `master-dev` 与文档 PR 上均以 `TOOL_VERSION_UNSUPPORTED` 失败，后续 `make ci` 步骤被跳过。该失败与具体业务 diff 无关，属于工具链契约与托管 runner 现实脱节。

SF02 本地依赖生命周期对 Docker `29.5.3` 与 Compose `5.1.4` 使用**字符串全等**预检；该路径与仓库级 `toolchain-check` 必须保持分离。

## 决策

在**同一份** `ops/workflow/toolchains.json` 中，用显式 **execution profile** 解释 system-managed 工具（当前为 Docker）的版本规则：

1. **Profile 必须显式声明**，优先级为：
   - CLI `--toolchain-profile`
   - 环境变量 `TOKENMARKET_TOOLCHAIN_PROFILE`
   - 默认 `local`
2. **不得**根据 `CI`、`GITHUB_ACTIONS` 或 `GITHUB_RUN_ID` 自动选择 profile。
3. **`local`（默认）**：使用工具项的 `exact_version` 与现有 `_version_matches` 语义（Docker 维持 `29.5.*` 前缀行为）。
4. **`github-actions-ubuntu-24.04`**：仅当工具项声明 `execution_overrides` 时，对该工具使用 `match: exact-list` 的 `allowed_versions` **精确字符串成员**判断；无 override 的工具（Go、Python、Node、uv 等）继续走原有 policy 与版本规则。
5. **Hosted 真实性证明**：当 profile 为 `github-actions-ubuntu-24.04` 时，还必须同时满足：
   - `GITHUB_ACTIONS` 严格等于 `true`
   - `RUNNER_OS` 严格等于 `Linux`
   否则 `INVALID_CONFIG`。GitHub Actions job 通过设置 `TOKENMARKET_TOOLCHAIN_PROFILE` 选择 profile；`GITHUB_ACTIONS` / `RUNNER_OS` 由 runner 内建提供，workflow 不得伪造。
6. **失败关闭**：未知 profile、hosted 证明失败、空 `allowed_versions`、未知 `match`、Docker 缺失、未批准版本均不得以 warning 或跳过 `toolchain-check` 的方式放行。
7. **schema_version**：`toolchains.json` 升为 `1.1.0`，表示增加可选 `execution_overrides` 字段。

当前 Docker hosted allowlist：

```text
28.0.4
29.5.3
```

## 非目标

- 不在 GitHub Actions 上安装 Docker Engine 29.5.3。
- 不修改 SF02 `local_env` preflight 的 Docker / Compose 全等规则。
- 不删除或不无条件跳过 `toolchain-check`。
- 不改变 Go、Python、Node、uv 的钉选与 install_policy 行为。
- 不根据隐式 CI 环境变量整表放宽工具链。

## 与 SF02 的边界

| 检查 | 入口 | Docker 规则 |
|------|------|-------------|
| 仓库级 `toolchain-check` | `make toolchain-check` / `make ci` preflight | profile 感知；local 维持 `29.5.*`；hosted 为 exact-list |
| SF02 生命周期 preflight | `make dev` / `start` | **始终** Docker `29.5.3` 与 Compose `5.1.4` 字符串全等 |

本地开发者即使手动设置 hosted profile，也无法通过 SF02 生命周期使用非 29.5.3 的 Docker。

## 维护

当 GitHub 更新 `ubuntu-24.04` runner 预装 Docker CLI 版本时：

1. 在 PR 中更新 `execution_overrides.github-actions-ubuntu-24.04.allowed_versions`；
2. 同步单元测试与 foundational 契约断言；
3. 确认 `quality-gate` 在真实 Actions 上通过；
4. 不得使用 `>=`、通配符或未登记版本的宽松范围。

## 回滚

一并回退：

- `ops/workflow/toolchains.json`（schema 与 overrides）
- `tools/workflow/cli.py` profile 逻辑
- `.github/workflows/ci.yml` 中的 `TOKENMARKET_TOOLCHAIN_PROFILE`
- 相关测试与本 ADR 的引用

保留作业名 `quality-gate` 与 `make ci` 公共入口。回退后托管 runner 将再次在 Docker 28.0.4 上失败，直至采用其他修复。

## 后果

### 正面

- 本地维护版本与托管 runner 现实可在同一清单中显式共存。
- Hosted 放宽范围可审计、可测试，且需 GITHUB 真实性证明。
- SF02 精确钉选不受影响。

### 负面

- Allowlist 需随 runner 镜像升级维护。
- 开发者可在本地设置 profile 环境变量；仅影响仓库级检查，不影响 SF02。

## 验证状态

**Accepted**。在真实 GitHub Actions `quality-gate` 绿色运行并留下证据前，本 ADR **不**标记为 Verified。

## 参考

- `ops/workflow/toolchains.json`
- `tools/workflow/cli.py`（`toolchain_check` / `resolve_toolchain_profile`）
- `.github/workflows/ci.yml`
- `shared/contracts/repository-workflow/v1/ci-gates.md`
- `shared/contracts/repository-workflow/v1/make-workflow.md`
- ADR 001、ADR 002
