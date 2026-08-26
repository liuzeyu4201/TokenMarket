**中文** | [English](README.en.md)

# TokenMarket

> 让 AI Coding Plan 的闲置额度流动起来。

TokenMarket 是 **AI Coding Plan 额度的实时撮合与代理平台**：卖家接入已有额度，买家用平台签发的代理 Key 按量调用；网关按 OpenAI 兼容协议转发到上游（V0.1 仅火山方舟）。

本仓库是实现该产品的 **monorepo**。当前处于 **V0.1 技术验证**：代理主链路与身份/Key API 已落地；计费撮合、多平台与完整业务前端仍在后续版本。

## 目录

- [当前范围](#当前范围)
- [架构](#架构)
- [快速开始](#快速开始)
- [仓库结构](#仓库结构)
- [公开命令](#公开命令)
- [文档](#文档)
- [安全](#安全)
- [许可](#许可)

## 当前范围

**已具备**

- 本地一键起停：中间件（PostgreSQL 15、Redis 7、Grafana OSS）+ 五个主机进程
- 用户注册、手机号验证登录、会话 Cookie、角色授权与自买自卖隔离
- 卖家 Key 接入 / 暂停 / 恢复 / 撤销（API）；买家代理 Key 签发 / 列表 / 撤销（API）
- 公开代理：`POST /v1/proxy/volcano/chat/completions`（非流式与 SSE 流式）
- Key 池轮询、上游容量保护、卖家 Key 健康检查、用量观察、结构化请求日志
- Grafana V0.1 代理总览看板与失败关闭的密钥/依赖扫描
- 测试/生产分层 Compose：`make deploy mode=test|prod`

**V0.1 不做**

- 计价、扣余额、Escrow、TMP 积分、提现与账单（计费服务仍为骨架）
- 智谱及其他平台；Embeddings / 非 Chat Completions
- 卖家挂售、买家充值、管理审核的完整 Web 产品页（前端目前为注册 / 登录 / 工作台占位）
- 将 Kafka 纳入本地 `make dev` 依赖集；把业务服务写进 `compose.local.yml`

产品意图与版本路线见 [`项目开发/产品需求文档（PRD）.md`](项目开发/产品需求文档（PRD）.md) 与 [`项目开发/产品迭代路线图.md`](项目开发/产品迭代路线图.md)。功能规格在 [`specs/`](specs/) 与 [`项目开发/V0.1/V0.1_0712/specs/`](项目开发/V0.1/V0.1_0712/specs/README.md)。

## 架构

```text
  浏览器 / OpenAI 兼容客户端
           │
           ├─ UI ──────────────────────────────► frontend :5173
           │                                      │ /api/v1（会话）
           │                                      ▼
           │                               api-service :8000
           │                               注册 · 登录 · 授权
           │                               卖家 Key · 代理 Key
           │
           └─ POST /v1/proxy/volcano/chat/completions
                                              │
                                       proxy-gateway :8080
                                       鉴权 · 选 Key · 转发 · 计量观察
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                  billing-service      admin-service         火山方舟上游
                  :8001 骨架           :8002 骨架
                         │
              PostgreSQL · Redis · Grafana :3000
```

- **proxy-gateway**（Go / Gin）：代理流量唯一入口。
- **api-service**（Python / FastAPI）：用户、授权与 Key 的领域所有者，第一迁移所有者。
- **billing-service**（Python / FastAPI）：第二迁移所有者；V0.1 无资金闭环。
- **admin-service**（Python / FastAPI）：管理面骨架，无数据库所有权。
- **frontend**（React 18 / Vite）：单一 Web 应用。
- **shared/contracts**：HTTP / 事件 / 工作流的版本化契约，先于消费者。

更完整的边界与数据流见 [`docs/architecture/`](docs/architecture/README.md)。工程最高约束是 [宪章](.specify/memory/constitution.md)。

## 快速开始

工具版本见 [`.tool-versions`](.tool-versions)：Go 1.25.14、Python 3.11.15、Node 24.18.0、uv 0.11.3。中间件需要本机 Docker。

```bash
make toolchain-check
make bootstrap
cp .env.example .env.local   # 将三个 tm_local_ 占位符换成独立合成密码
make start
make migrate
```

之后日常只需要：

```bash
make start
make stop
```

第一次配密码、端口、恢复码见 [`QUICKSTART.md`](QUICKSTART.md)。验证：

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

| 用途 | 地址 |
|------|------|
| 前端 | http://127.0.0.1:5173 |
| 注册 / 登录 / 工作台 | `/register` · `/login` · `/dashboard` |
| 网关健康 | http://127.0.0.1:8080/health/live |
| API 就绪 | http://127.0.0.1:8000/health/ready |
| Grafana | http://127.0.0.1:3000 |
| 公开代理 | `POST http://127.0.0.1:8080/v1/proxy/volcano/chat/completions` |

业务进程跑在本机，**不**进入 `infra/docker/compose.local.yml`。

## 仓库结构

```text
.
├── services/proxy-gateway   # Go 网关：健康、metrics、火山代理
├── services/api-service     # 用户 / 授权 / Key API，迁移顺序 1
├── services/billing-service # 计费骨架，迁移顺序 2
├── services/admin-service   # 管理骨架
├── frontend                 # React 18 前端
├── shared/contracts         # 版本化契约（机器可读，权威）
├── infra                    # Compose、Grafana、镜像资产
├── ops                      # 运行手册、告警、迁移所有权
├── tools/workflow           # 根 Makefile 背后的工作流 CLI
├── tests/workflow           # 根级工作流契约测试
├── specs                    # Spec Kit 功能规格与验收证据
├── docs                     # 文档枢纽（分类索引 + ADR）
├── 产品调研                 # 市场、竞品、商业计划（权威原文）
└── 项目开发                 # PRD、路线图、工程规范（权威原文）
```

## 公开命令

根 [`Makefile`](Makefile) 是唯一公共入口。`make help` 列出用途、副作用与恢复。

| 命令 | 用途 |
|------|------|
| `make start` / `make stop` | **本地默认**：中间件 + 五个主机进程；每次启动重读 `.env.local` |
| `make dev` / `make dev-down` | 只管理 PostgreSQL / Redis / Grafana |
| `make start scope=apps` | 中间件已就绪时只操作应用进程 |
| `make deploy` / `make deploy-down` | 测试/生产全栈；必须 `mode=test\|prod` |
| `make fmt` / `make lint` / `make test` | 格式化、静态检查、全部测试 |
| `make build` | 五个服务镜像与三个确定性资产包 |
| `make migrate` | 按所有者顺序执行已评审 Alembic 迁移 |
| `make ci` | 与 GitHub Actions `quality-gate` 相同的完整顺序 |
| `make bootstrap` / `make type-check` | 准备已提交锁的依赖；独立类型检查 |

分层：本地 = 主机应用 + 中间件；测试/生产 = `make build` 后 `make deploy mode=…`。环境**不**从 Git 分支名推断。

`.github/workflows/ci.yml` 只调用 `make ci`。项目逻辑留在 Makefile 与 `tools/workflow/`。

## 文档

分类地图与语言约定：[`docs/README.md`](docs/README.md) · [English](docs/README.en.md)

| 读者 | 从这里开始 |
|------|------------|
| 第一次跑起来 | [QUICKSTART.md](QUICKSTART.md) · [English](QUICKSTART.en.md) |
| 改代码、开 PR | [CONTRIBUTING.md](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md) |
| 看架构与 ADR | [docs/architecture](docs/architecture/README.md) · [docs/decisions](docs/decisions/README.md) |
| 查 HTTP 契约 | [docs/api](docs/api/README.md) → [`shared/contracts/`](shared/contracts/README.md) |
| 产品与调研 | [docs/product](docs/product/README.md) |
| 本地/部署排障 | [ops/runbooks](ops/runbooks/README.md) |
| 报告安全问题 | [SECURITY.md](SECURITY.md) |

## 安全

- 真实配置只存在于被忽略的 `.env.local`；[`.env.example`](.env.example) 仅含不可用占位符。
- gitleaks、govulncheck、pip-audit、npm audit **失败关闭**。
- 生产动作必须显式 `mode=prod` 并经独立审批。
- 卖家上游 Key 认证加密存储；日志与错误不得出现完整凭证。

细则见 [SECURITY.md](SECURITY.md) 与 [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md)。

## 许可

[Proprietary](LICENSE) — 未经许可不得使用、复制或分发。
