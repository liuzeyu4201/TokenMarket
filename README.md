# TokenMarket

> 可验证、可复现的 AI 服务与 Token 交易市场工程基线。

TokenMarket 是一个面向 AI 流量代理与 Token 交易场景的 monorepo 工程基线。当前处于 **V0.1 / SF01** 阶段：本仓库仅建立跨服务开发、测试、构建、迁移与持续集成的统一工作流，尚未实现买家、卖家、提供商 Key、代理路由、计量计费等业务能力。

## 当前阶段

**SF01 — 仓库工程工作流基线**

- 单一根入口：`make help`、`make fmt`、`make lint`、`make test`、`make build`、`make migrate`、`make ci`
- 八个职责清晰的组件边界：Go 网关、三个 Python 服务、React 前端、共享契约、基础设施定义、运维资产
- 本地与 GitHub Actions 使用同一套 `make ci` 质量门禁
- 安全配置、秘密扫描、依赖扫描与生产审批契约已就位
- 所有必需组件具备真实可运行的最小骨架与冒烟测试

## 技术栈

| 层级 | 技术 |
|------|------|
| 网关 | Go 1.25.12、Gin、Prometheus |
| 后端服务 | Python 3.11.15、FastAPI、Pydantic、SQLAlchemy、Alembic、asyncpg |
| 前端 | React 18、TypeScript（strict）、Vite、Vitest、ESLint、Prettier |
| 工程工具 | uv、npm、Docker、Make、GitHub Actions |
| 可观测与基础设施 | Prometheus 指标、Grafana/Kafka/PostgreSQL 定义（SF02 实现生命周期） |

## 快速开始

只需安装受支持的工具链版本（见 `.tool-versions`），然后：

```bash
make toolchain-check   # 验证工具版本
make bootstrap         # 安装锁定依赖
make test              # 运行所有组件测试
make lint              # 静态分析与边界检查
make build             # 构建五镜像与三资产包
make ci                # 本地复现完整 CI 门禁
```

完整路径见 [`specs/001-repository-workflow-baseline/quickstart.md`](specs/001-repository-workflow-baseline/quickstart.md)。

## 项目结构

```text
.
├── services/proxy-gateway   # Go 入口网关（健康、metrics、request ID）
├── services/api-service     # 核心 API 服务与首个迁移所有者
├── services/billing-service # 计费服务与第二个迁移所有者
├── services/admin-service   # 管理服务（无数据库所有权）
├── frontend                 # React 18 可访问前端骨架
├── shared                   # 版本化契约与共享验证工具
├── infra                    # 基础设施定义（生命周期阻塞在 SF02）
├── ops                      # 迁移所有权、runbook、监控与备份资产
├── tools/workflow           # 仓库工作流 CLI（事件、清单、模式、扫描）
├── tests/workflow           # 根级工作流契约测试
└── docs/decisions           # 架构决策记录（ADR）
```

## 公开工作流入口

| 命令 | 用途 |
|------|------|
| `make dev` / `make dev-down` | 本地依赖生命周期（SF02 前返回 `SF02_NOT_READY`） |
| `make fmt` | 应用仓库格式化工具 |
| `make lint` | 汇总静态分析、类型检查与边界检查 |
| `make test` | 汇总所有组件自动化测试 |
| `make build` | 构建五个服务镜像与三个确定性资产包 |
| `make migrate` | 按所有者顺序执行已评审迁移 |
| `make ci` | 本地复现 hosted `quality-gate` 的完整顺序 |

## 安全与合规

- 真实配置只能通过 `.env.local` 等被忽略文件注入；`.env.example` 仅含不可用占位符。
- 秘密扫描（gitleaks）、Go 漏洞扫描（govulncheck）、Python 依赖扫描（pip-audit）、npm audit 均失败关闭。
- 生产动作必须通过 `mode=prod` 显式选择并经过独立审批。
- 详见 [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md)。

## 持续集成

`.github/workflows/ci.yml` 是一个只读薄适配层，仅执行：

```bash
make ci
```

所有项目逻辑保留在根 `Makefile` 与 `tools/workflow/` 中，CI 平台可替换而无需修改项目行为。

## 状态

- `make test` / `make lint` / `make fmt-check`：通过
- `make ci`：当前因已知 `starlette 0.45.3` 依赖漏洞失败关闭；修复前不启用 required check
- 文档与证据：`specs/001-repository-workflow-baseline/checklists/`

## License

Proprietary — 未经许可不得使用、复制或分发。
