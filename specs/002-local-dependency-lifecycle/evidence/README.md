# SF02 验收证据索引（T072）

所有者：repository workflow owner

公共激活 `make dev` / `make dev-down` 与默认 event v2 要求下表**全部**行通过。下表行达到 PASS 后，**T074 于 2026-07-25 激活**。

| 产物 | 任务 | 状态 |
|----------|------|--------|
| [quality-gates.md](./quality-gates.md) | T068 | **PASS** — 工具链至构建 + image-scan 绿灯（2026-07-22） |
| [linux-amd64.md](./linux-amd64.md) | T069 | **PASS** — 2026-07-24；harness `21bbd96`；25/25 矩阵（WSL2 Ubuntu + Docker Desktop Linux engine） |
| [macos-arm64.md](./macos-arm64.md) | T070 | **PASS** — Darwin arm64 上 20/20 冷启动 + 10/10 重复（2026-07-22） |
| [developer-usability.md](./developer-usability.md) | T071 | **PASS** — 负责人授权的仅基于文档的易用性验证协议（2026-07-25） |
| ADR 002 实现验证 | T073–T074 | 设计 **Accepted**；验证 **Verified**（T074, 2026-07-25） |


## Quickstart 场景（安全 / 当前分支）

| 章节 | 场景 | 本分支状态 |
|---------|----------|--------------------|
| 1 | `make help` | **PASS** |
| 1 | `make toolchain-check` | **PASS**（T069 已提交审计 2026-07-24） |
| 2 | `.env.example` / ignore 策略 | 已文档化；不得提交 `.env.local` |
| 3–8 | 公共 `make dev` / `dev-down` 冷启动、重复、停止、标记 | **Activated at T074** — 真实生命周期；由单元/集成 + 双平台测试框架覆盖 |
| 9–10 | 自动化 `make test` SF02 覆盖 | 离线套件 **PASS**（见 quality-gates） |
| 11 | 双平台测试框架 | **Linux T069 PASS**（2026-07-24, `21bbd96`）；**macOS T070 PASS**（2026-07-22） |
| 12 | 验收证据包 | 本索引 |

## 相关文档

- Spec / plan / tasks: `specs/002-local-dependency-lifecycle/`
- 运行手册: `ops/runbooks/local-environment.md`
- ADR: `docs/decisions/002-local-compose-lifecycle.md`
- Digests: `ops/workflow/local-dependencies.json`

## 脱敏规则

永不包含密钥、含 user-info 的完整 URL、工作区路径或原始 Docker stderr。仅汇总计时与 pass/fail。
