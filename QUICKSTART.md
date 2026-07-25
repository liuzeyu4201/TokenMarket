# TokenMarket 本地开发快速开始

目标很简单：完成一次性准备后，日常开发只记两条命令。

```bash
make start
make stop
```

- `make start`：启动或复用 PostgreSQL、Redis、Grafana，以及
  gateway、api、billing、admin、frontend 五个主机进程。
- `make stop`：先停应用进程，再停中间件；保留 PostgreSQL/Redis 数据。
- 每次启动都会重新读取并校验 `.env.local`；受管理配置变化时自动重启对应应用，
  不会让健康进程继续使用旧环境变量。
- 应用进程始终运行在本机，不加入 `infra/docker/compose.local.yml`。

> **当前激活状态**
>
> SF02 中间件公共生命周期仍等待 T071/T074，因此当前分支的默认
> `make start` / `make stop` 会以 `SF02_NOT_READY` 安全退出，不会通过新入口
> 绕过门禁。若中间件已由外部方式准备好，可先使用
> `make start scope=apps` / `make stop scope=apps` 管理应用进程。

## 第一次准备

### 1. 检查工具并安装锁定依赖

```bash
make toolchain-check
make bootstrap
```

所需版本见 `.tool-versions`。启动中间件时还需要可用的本地 Docker daemon。

### 2. 创建本地配置

```bash
cp .env.example .env.local
```

`.env.local` 已被 Git 忽略。为三个密码分别生成不同的本地合成值：

```bash
python3 -c 'import secrets; print("tm_local_" + secrets.token_urlsafe(24))'
```

替换以下字段中的占位符：

```text
MODE=local
DATABASE_URL=postgresql://app:tm_local_<secret>@127.0.0.1:5432/tokenmarket
REDIS_URL=redis://default:tm_local_<different-secret>@127.0.0.1:6379/0
GRAFANA_URL=http://127.0.0.1:3000
GRAFANA_ADMIN_PASSWORD=tm_local_<third-secret>
```

约束：

- 主机必须是字面量 `127.0.0.1`，不能使用 `localhost`、`0.0.0.0` 或局域网地址。
- PostgreSQL、Redis、Grafana 端口只由这三个 URL 决定。
- Shell 中的 `POSTGRES_HOST_PORT`、`REDIS_HOST_PORT`、
  `GRAFANA_HOST_PORT` 不会覆盖 `.env.local`。
- 不要提交 `.env.local`，也不要把其中内容复制到日志、Issue 或 PR。

`make start` 不会自动生成或轮换这些密码。自动轮换会让已持久化的
PostgreSQL/Redis 数据卷与新凭据失配；需要变更密钥时，应按恢复流程同时处理
持久化依赖。工作流只保存不可逆的应用配置指纹，不把连接 URL 或密钥写入状态文件。

### 3. 首次启动并显式迁移

SF02 公共激活完成后：

```bash
make start
make migrate
```

`make migrate` 从 `.env.local` 安全读取本地数据库地址，并按照
API Service → Billing Service 的所有者顺序执行迁移。启动不会自动迁移、
重置或填充数据库。

之后的日常启动只需要：

```bash
make start
```

## 命令一览

### 日常入口

| 命令             | 行为                                         |
| ---------------- | -------------------------------------------- |
| `make start`   | 启动或复用完整本地环境                       |
| `make stop`    | 停止完整本地环境，保留 PostgreSQL/Redis 数据 |
| `make migrate` | 显式执行已评审迁移；不负责启动数据库         |

### 进阶入口

| 命令                                        | 使用场景                                                   |
| ------------------------------------------- | ---------------------------------------------------------- |
| `make dev`                                | 只启动 PostgreSQL、Redis、Grafana；SF02 激活前 fail-closed |
| `make dev-down`                           | 只停止中间件，保留 PostgreSQL/Redis 数据                   |
| `make start scope=apps`                   | 中间件已就绪时，只启动或复用五个主机进程                   |
| `make stop scope=apps`                    | 只停止由当前工作区管理的主机进程                           |
| `make start scope=apps RESTART_PROCESS=1` | 强制重启主机进程                                           |

`scope=apps` 是排障和局部开发选项，不属于日常主路径。中间件专用操作继续使用
稳定的 `make dev` / `make dev-down`，不再提供重复的 `scope=stack` 入口。

## 服务地址

| 服务            | 默认地址                  | 覆盖方式                               |
| --------------- | ------------------------- | -------------------------------------- |
| PostgreSQL      | `127.0.0.1:5432`        | 修改`.env.local` 的 `DATABASE_URL` |
| Redis           | `127.0.0.1:6379`        | 修改`.env.local` 的 `REDIS_URL`    |
| Grafana         | `http://127.0.0.1:3000` | 修改`.env.local` 的 `GRAFANA_URL`  |
| proxy-gateway   | `http://127.0.0.1:8080` | `GATEWAY_HOST_PORT=…`               |
| api-service     | `http://127.0.0.1:8000` | `API_HOST_PORT=…`                   |
| billing-service | `http://127.0.0.1:8001` | `BILLING_HOST_PORT=…`               |
| admin-service   | `http://127.0.0.1:8002` | `ADMIN_HOST_PORT=…`                 |
| frontend        | `http://127.0.0.1:5173` | `FRONTEND_HOST_PORT=…`              |

应用端口示例：

```bash
make start scope=apps API_HOST_PORT=18000 FRONTEND_HOST_PORT=15173
```

前端的 API 基址会同步指向当前 API 端口。

## 成功后检查

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

常用页面：

- 注册页：`http://127.0.0.1:5173/register`
- Grafana：`http://127.0.0.1:3000`

`/health/live` 只表示进程存活；依赖数据库的功能还需要 readiness 和迁移成功。

## 失败与恢复

启动输出会包含阶段、组件、稳定错误码和下一步恢复动作。修复后重复执行同一命令。

| 错误码                   | 含义                                       | 恢复                                             |
| ------------------------ | ------------------------------------------ | ------------------------------------------------ |
| `SF02_NOT_READY`       | 中间件公共激活门禁尚未完成                 | 完成 T071/T074；不要调用内部 guarded adapter     |
| `INVALID_CONFIG`       | `.env.local` 缺失、含占位符或 URL 不合法 | 对照模板修复后重试                               |
| `TOOL_MISSING`         | 工具或 Docker daemon 不可用                | 启动/安装声明版本后重试                          |
| `PORT_CONFLICT`        | 端口被其他进程占用                         | 释放端口；中间件端口只改 URL，应用端口用对应变量 |
| `DEPENDENCY_NOT_READY` | 中间件健康探针超时                         | 查看安全诊断，修复后重试`make start`           |
| `APP_NOT_READY`        | 一个或多个应用进程未达到 liveness          | 查看输出给出的 runtime 日志位置                  |

如果 `.env.local` 或应用端口发生变化，下一次 `make start` 会输出
`action=restart reason=config_changed`，随后用新环境重新拉起对应进程。

应用 stdout/stderr 位于按工作区哈希隔离的安全 runtime 目录，不写入仓库。

## 不要这样启动

- 不要直接执行 `docker compose -f infra/docker/compose.local.yml up`。
- 不要把业务服务加入 `compose.local.yml`。
- 不要运行 `make deploy mode=local`；部署只允许 `mode=test|prod`。
- 不要在 Shell 中覆盖中间件端口；修改 `.env.local` 中对应 URL。
- 不要依赖组件目录里的直接启动命令作为日常入口；它们仅用于维护和诊断。

测试/生产整栈使用：

```bash
make build
make deploy mode=test
```

更多信息：

- `make help`
- `ops/runbooks/local-environment.md`
- `ops/runbooks/deploy.md`
- `README.md`
