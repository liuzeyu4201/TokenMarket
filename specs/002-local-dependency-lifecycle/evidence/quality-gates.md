# 质量门禁验收证据（SF02 / T068）

**状态**： **PASS**，于 macOS arm64（Darwin），Node 24.18.0、Go 1.25.12、Docker 可用、Trivy 0.72.0。

## 环境（已脱敏）

| 项 | 值 |
|------|--------|
| OS | Darwin arm64 |
| Node | 24.18.0 |
| Go | 1.25.12 |
| Python | 3.11.15 / uv |
| Docker | available |
| Trivy | 0.72.0 |
| Date | 2026-07-22 |

## 门禁结果

| 门禁 | 结果 | 说明 |
|------|--------|-------|
| `make help` | **PASS** | |
| `make toolchain-check` | **PASS** | |
| `make fmt-check` | **PASS** | |
| `make type-check` | **PASS** | |
| `make lint` | **PASS** | |
| `make test` | **PASS** | Aggregate PASSED |
| `make migrate-check` | **PASS** | |
| `make security-check` | **PASS** | gitleaks config + pip-audit + govulncheck |
| `make bootstrap` | **PASS** | |
| `make build` | **PASS** | 9 components; ~9–10 min |
| `make image-scan` | **PASS** | 5/5 images, 0 HIGH/CRITICAL with fix available |
| Public `dev` / `dev-down` | **PASS**（fail-closed） | 在 T074 前仍为 `SF02_NOT_READY` |

## 为本门禁应用的安全 / 镜像加固

1. **Trivy** 已安装（`brew install trivy`）。
2. **`.gitleaks.toml`** 允许合成本地测试/文档凭据；`security.py` 传入 `--config`。
3. **Python services**: FastAPI 0.139.2 + Starlette 1.3.1；Dockerfile 升级基座 `setuptools`/`wheel`/`jaraco.context`。
4. **proxy-gateway**: Go 依赖 `x/net`/`x/crypto` 提升；镜像在 Trivy 下重建干净。
5. **frontend**: `nginx:1.29-alpine` + `apk upgrade`。
6. **image-scan**: 发出每组件事件；Trivy 使用 `--ignore-unfixed`，因此仅可修复的 HIGH/CRITICAL 阻塞门禁。

## 本门禁之外（后续任务）

- 双平台性能测试框架 → **T069 / T070**
- 十人易用性 → **T071**
- 公共激活 → **T074**（在 T069–T071 通过前不要执行）

## 工具链漂移说明（T084）

**固定契约**（不得放宽）：`ops/workflow/toolchains.json` 与
`.tool-versions` 要求 **Node 精确 `24.18.0`**（npm 随该发行捆绑）。
CI 与验收证据主机必须匹配。

| 情况 | 恢复 |
|-----------|----------|
| 主机默认 Node 为 `24.13.x`（或其他非精确版本） | `nvm install 24.18.0 && nvm use 24.18.0`（或等效 asdf/mise），然后重跑 `make toolchain-check` |
| 根 `make build` 因 node 的 `TOOL_VERSION_UNSUPPORTED` 失败 | 同上；组件 `make -C services/*/ build` 仍可经仅 Docker 路径工作，但**不是**根门禁的替代 |
| 有意变更固定版本 | 经评审 PR 一并更新 `.tool-versions` + `toolchains.json` 完整性引用 |

**本会话（2026-07-22, later）**: 默认 shell Node 为 `24.13.0`；在
`nvm use 24.18.0` 之后，`make toolchain-check` 返回 0。固定版本仍为
`24.18.0` — 主机漂移是操作者恢复问题，而非契约降级。

## 结论

SF02 所需的 T068 离线 + Docker 质量矩阵记录为 **PASS**。公共生命周期在当时仍保持失败关闭。
