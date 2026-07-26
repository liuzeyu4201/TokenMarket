# 入门证据

**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14
**场景**：代表性新开发者首次设置

## 目标

新贡献者应当仅使用仓库文档化的入口，在 15 分钟内从全新检出
推进到本地 `make test` 通过。

## 已执行路径

| 步骤 | 命令 | 预期结果 | 实际结果 | 时间 |
|------|---------|-----------------|---------------|------|
| 1 | `make help` | 在 2 秒内列出目标 | Passed | <1 s |
| 2 | `make toolchain-check` | 确认固定工具版本 | Passed | <2 s |
| 3 | `cp .env.example .env.local` | 创建被忽略的本地配置 | Passed | <1 s |
| 4 | `make bootstrap` | 安装已锁定的依赖 | Passed | ~30 s |
| 5 | `make test` | 全部组件测试通过 | Passed | ~60 s |

总墙钟时间：约 95 秒，远低于 15 分钟目标。

## 观察到的阻塞点

1. **工具链可用性**：工作站已具备固定版本的 Go、Python、
   uv、Node 与 Docker。没有这些工具的机器需要先安装
   工具；这超出仓库工作流范围，但应当
   在贡献者指南中文档化。
2. **Trivy 镜像扫描**：`make image-scan` 需要单独安装 Trivy；
   它不由 `make bootstrap` 提供。这与 fail-closed 设计一致，
   但是已知的首次摩擦点。
3. **Starlette 依赖发现**：`make security-check` 报告已知的
   `starlette` 漏洞。新开发者不得忽略此点；它被跟踪为合并前的
   必需修复或已批准例外。

## 已记录的修订

- 在根 `README.md` 中新增明确的「前置条件」章节，列出所需
  工具版本。
- 从 `README.md` 链接到 `ops/runbooks/workflow.md`，以获取 CI 恢复与
  扫描器安装说明。

## 成功率

文档化 15 分钟路径的单次尝试成功：**100%**。
