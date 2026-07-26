# US1 工作流证据

**功能**：specs/001-repository-workflow-baseline — 仓库工程工作流基线
**故事**：US1 — 从仓库根目录完成日常工程动作
**记录日期**：2026-07-15
**环境**：macOS, Go 1.25.12, Python 3.11.15, Node 24.18.0, Docker Desktop

## 1. 根 Makefile 帮助

```text
TokenMarket repository workflow

Public targets:
  make dev            Start local dependencies after SF02
  make dev-down       Stop local dependencies after SF02
  make fmt            Apply repository formatters (modifies source)
  make lint           Run static analysis, type checks and boundary checks
  make test           Run all component tests
  make build          Build five service images and three asset bundles
  make migrate        Apply reviewed migrations to selected environment

Support targets:
  make bootstrap      Prepare locked project dependencies
  make type-check     Run the complete type-check set independently
  make toolchain-check Verify declared tool versions

Prerequisites: Go, Python/uv, Node/npm, Docker (see .tool-versions)
Side effects: fmt modifies declared source files; build creates local images
Recovery: fix the reported component error and rerun the same command
```

## 2. 冻结 Bootstrap 幂等性

连续两次 `make bootstrap` 运行完成时，未修改任何锁文件
或依赖解析：

- 第一次运行：为 tools/workflow、api-service、billing-service、
  admin-service 安装/验证了 uv 环境；为 frontend 运行了 `npm ci`。
- 第二次运行：所有 Python 项目均为 `Resolved ... Checked ...`；`npm ci`
  报告 `up to date`。

各次运行之间未观察到 `uv.lock` 或 `package-lock.json` 漂移。

## 3. 独立类型检查

```text
[PASSED] repository type-check: [OK] aggregate type-check: {'status': 'PASSED', 'code': 'OK', 'passed': 9, 'failed': 0, 'skipped': 0}
```

全部八个组件加上仓库工作流工具均通过了各自的
类型检查（Go vet/golangci-lint、mypy、tsc --noEmit）。

## 4. 聚合测试 / 静态检查 / 构建

| 命令 | 结果 | 通过 | 失败 | 跳过 |
|---------|--------|--------|--------|---------|
| `make test` | PASSED | 9 | 0 | 0 |
| `make lint` | PASSED | 9 | 0 | 0 |
| `make build` | PASSED | 9 | 0 | 0 |

### 组件测试计数

| 组件 | 测试数量 | 运行器 |
|-----------|------------|--------|
| proxy-gateway | 7 | go test -race |
| api-service | 7 | pytest |
| billing-service | 5 | pytest |
| admin-service | 8 | pytest |
| frontend | 4 | vitest |
| shared | 6 | pytest |
| infra | 9 | pytest |
| ops | 10 | pytest |
| **合计** | **56** | — |

### 工作流契约测试

`tests/workflow` 套件：**126 通过，0 失败**。

## 5. PostgreSQL 15 迁移往返

```text
[PASSED] repository migrate-check: [OK] migration owners validated: api-service, billing-service; mode=local
[PASSED] repository migrate-integration-check: [OK] api-service and billing-service forward/backout/retry passed on isolated PostgreSQL 15
```

- `migrate-check` 验证了 `api-service` 与 `billing-service` 是仅有的
  迁移所有者，`admin-service` 列为非所有者。
- `migrate-integration-check` 在隔离的 PostgreSQL 15 容器上运行了
  API→Billing 的前向、回退、重试与最终 head 恢复，未调用
  `make dev`，也未共享数据库。

## 6. 五个镜像运行时冒烟

构建并冒烟测试了具有独立构建上下文、多阶段
Dockerfile、非 root 用户与健康检查的镜像：

| 镜像 | 标签 | 大小 | 健康冒烟 |
|-------|-----|------|--------------|
| tokenmarket/proxy-gateway | 0.1.0 | 19.8 MB | PASSED |
| tokenmarket/api-service | 0.1.0 | 275 MB | PASSED |
| tokenmarket/billing-service | 0.1.0 | 281 MB | PASSED |
| tokenmarket/admin-service | 0.1.0 | 229 MB | PASSED |
| tokenmarket/frontend | 0.1.0 | 76.8 MB | PASSED |

## 7. 三个资产包摘要

`make build` 生成了确定性资产归档：

| 包 | 路径 | 大小 |
|--------|------|------|
| shared-contracts | `shared/dist/shared-contracts.tar.gz` | 8.8 KB |
| infra-assets | `infra/dist/infra-assets.tar.gz` | 607 B |
| ops-assets | `ops/dist/ops-assets.tar.gz` | 1.6 KB |

## 8. SF02 零副作用门禁

`make dev` 与 `make dev-down` 均在读取配置或访问 Docker 之前
以 `SF02_NOT_READY` 失败：

```text
[FAILED] repository dev: [SF02_NOT_READY] SF02 must provide the lifecycle adapter
[FAILED] repository dev-down: [SF02_NOT_READY] SF02 must provide the lifecycle adapter
```

未启动、停止或修改任何本地资源。

## 9. 已知本地环境说明

- 验证会话中通过 nvm 将 Node 切换为 `v24.18.0`。
- 在 `~/.local` 下安装了 Go 1.25.12 与 golangci-lint 1.64.8，以匹配
  工具链清单，因为主机版本不一致。
- 根据 Node.js 下载归档，更新了 `ops/workflow/toolchains.json` 以记录
  随 Node 24.18.0 附带的实际 npm 版本（`11.16.0`）。
- 扩展了 `tools/workflow/manifest.py`，除 `test_*` 与 `*_test.*` 外
  还接受 `*.test.*` 测试文件，以匹配前端 Vitest 约定。

## 10. 签核

US1 实现满足根级工程动作的验收标准：
稳定的 Makefile 入口、真实的按组件格式化/类型检查/
测试/构建、不可变镜像标签、隔离的 PG15 迁移验证，以及
SF02 过渡护栏。
