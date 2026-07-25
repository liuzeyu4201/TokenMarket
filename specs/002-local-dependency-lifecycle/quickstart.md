# 快速验收：本地依赖环境生命周期

**Feature**: `002-local-dependency-lifecycle`
**Purpose**: 实现后的可运行验收指南；破坏性、并发与故障注入场景仍以自动化测试为准
**Safety**: 仅使用合成本地凭据与数据。切勿将这些命令指向测试/生产资源。

## 1. 校验维护中的主机工具链

在仓库根目录：

```bash
make help
make toolchain-check
```

预期：

- 帮助仍说明 `make dev` 和 `make dev-down` 是唯一的公共本地依赖生命周期入口，并说明副作用/恢复。
- Docker 29.5.3 与 Compose 5.1.4 在不做安装或升级的情况下通过校验。
- daemon 在 macOS arm64 或 Linux x86_64 上为可到达的本地 Linux 容器端点；远程 context 在访问配置/资源前失败。
- 输出不含环境变量值或绝对工作区路径。
- Docker/Compose 标签仅包含 Compose 所需的安全 runtime 项目目录；原始或规范化工作区路径均不得出现在任何标签中。

若 Docker Desktop/Engine 已停止或当前用户无权限，在仓库外修复后重跑。工作流不得调用 `sudo`、改组或启动系统服务。

## 2. 准备被忽略的合成本地配置

```bash
cp .env.example .env.local
git check-ignore .env.local
python3 -c 'import secrets; print("tm_local_" + secrets.token_urlsafe(24))'
```

为每个 SF02 密码占位符使用独立生成的值。每个解码后的值必须以 `tm_local_` 开头，前缀后为 32–96 个 URL-safe 字符。字段形状如下：

```text
MODE=local
DATABASE_URL=postgresql://<local-user>:tm_local_<32-96-url-safe-chars>@127.0.0.1:5432/<local-database>
REDIS_URL=redis://default:tm_local_<different-32-96-url-safe-chars>@127.0.0.1:6379/0
GRAFANA_URL=http://127.0.0.1:3000
GRAFANA_ADMIN_PASSWORD=tm_local_<third-32-96-url-safe-secret>
```

预期：

- `git check-ignore` 打印 `.env.local`；`git status --short` 不列出它。
- 密码为合成值，且仅用于本本地工作区。
- 三个 URL 是唯一的主机/端口事实源；不创建 `POSTGRES_PORT`、`REDIS_PORT`、独立容器 URL 或 Compose override。
- 不得把生成值贴进 Issue、PR、测试夹具或验收记录。

## 3. 冷启动（有或无缓存镜像）

```bash
make dev
```

预期：

- 输出给出安全的 `tokenmarket-<12-hex>` 项目 ID，且永不打印源路径。
- 若镜像缺失，分别为 `postgres`、`redis`、`grafana` 出现独立的 `image-pull` 事件；仅拉取已提交的 digest 身份。
- 60 秒就绪检查（readiness）计时在所有镜像身份本地可用后开始。
- Compose 状态协调（reconcile）与全部三个即时执行的认证探针在该单一截止时间内完成；没有第二次 post-wait 探针预算。
- 最终逐依赖验收证据显示：
  - PostgreSQL 认证查询就绪；
  - Redis 认证 `PING` 就绪；
  - Grafana 健康数据库与管理员身份就绪。
- 主机端点展示不含 user-info/密码，且仅使用 `127.0.0.1`。
- 仅当三者均就绪时聚合退出码为 0。Kafka/Redpanda、Prometheus、Loki、MinIO、frontend、gateway 与 Python 服务均不启动。
- JSONL 输出校验为标准 event v2 信封：唯一事件 ID、UTC 时间戳、稳定 producer/type、一个生命周期 correlation ID 与严格依赖 payload；纯文本传达相同安全状态，不依赖颜色、图标、动画或交互。

若就绪检查失败，不得删除卷。按报告的依赖/错误码处理，仅使用运行手册中描述的安全诊断命令，修复原因后再次运行 `make dev`。

## 4. 确认幂等的重复启动

对健康环境连续执行十次：

```bash
make dev
```

每次运行预期：

- 15 秒内完成。
- 无 registry 访问或镜像拉取。
- 相同项目 ID、服务、网络与 PostgreSQL/Redis 卷身份。
- 无重复容器、网络、命名卷或 Grafana 匿名卷。
- 仅因确认而启动时，PostgreSQL 与 Redis 内容不被改动。

自动化集成测试在十次运行前后捕获资源计数；手工验收不必解析 Docker 表格输出。

## 5. 校验稳定的主机与容器连接契约

成功的 `make dev` 就绪检查探针已验证主机地址与认证操作。对照安全输出与 [`contracts/local-environment-lifecycle.md`](./contracts/local-environment-lifecycle.md)：

| 依赖 | 主机进程地址 | 容器网络地址 |
|------------|----------------------|---------------------------|
| PostgreSQL | 来自 `DATABASE_URL` 的 URL | 同一 URL，主机改为 `postgres:5432`，保留原用户/库名 |
| Redis | 来自 `REDIS_URL` 的 URL | 同一 URL，主机改为 `redis:6379`，保留原 DB 编号 |
| Grafana | 来自 `GRAFANA_URL` 的 URL | `http://grafana:3000` |

预期：

- 主机发布绑定 `127.0.0.1`，不是 `0.0.0.0`。
- 容器 DNS 名在项目网络上恰好为 `postgres`、`redis`、`grafana`。
- 不存在由开发者维护的第二套容器 URL。

真实集成套件会在精确项目网络上创建短生命周期、仅测试用的容器。它通过 stdin 接收合成探针材料，再使用规范容器 URL 执行 PostgreSQL 查询、Redis AUTH/PING 与 Grafana health/admin HTTP 请求。仅 DNS 解析不算通过。探针密钥不进入 argv、环境、inspect 输出或保留验收证据，且探针从不是 `make dev` 成功条件的一部分。

## 6. 校验 API Service 的 PostgreSQL 就绪检查

依赖运行后，在另一终端启动 API Service，不得复制配置：

```bash
cd services/api-service
uv run --locked --env-file ../../.env.local uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再开终端：

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

预期：

- Liveness 为 200，`status=alive`。
- 就绪检查为 200，成功形状与 SF01 一致，`status=ready`。
- 响应/日志中不出现 URL、用户名、SQL 异常或密码。
- `/metrics` 在成功就绪检查探针时递增 `tokenmarket_postgres_readiness_probes_total`、观察 `tokenmarket_postgres_readiness_probe_duration_seconds`，且 `tokenmarket_postgres_readiness_probe_failures_total` 不变；任何 metric 标签都不含配置或异常数据。

仅通过自动化套件拥有的测试故障注入辅助停止 PostgreSQL（本指南中不得手改或删除卷）。服务契约测试证明：

- liveness 仍为 200；
- 就绪检查在两秒探针边界内变为 503；
- 响应体仅命名 `postgres` 与稳定安全码；
- 总计数与失败计数递增，duration histogram 观察失败探针；
- PostgreSQL 恢复后，无需重启 API Service 即可回到就绪检查 200。

## 7. 校验 Billing Service 的 PostgreSQL 就绪检查

在不同端口重复上一流程：

```bash
cd services/billing-service
uv run --locked --env-file ../../.env.local uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```bash
curl -fsS http://127.0.0.1:8001/health/live
curl -fsS http://127.0.0.1:8001/health/ready
```

预期行为、指标与恢复与 API Service 相同。Gateway 与 Admin Service 必须保持 SF01 就绪检查行为，且不得在 SF02 中获得 PostgreSQL 就绪检查探针。

继续前先停止本地 Uvicorn 进程。它们不由 `make dev-down` 做生命周期管理。

## 8. 非破坏性停止与重复停止

```bash
make dev-down
make dev-down
```

预期：

- 第一次调用在有界优雅终止后，仅移除精确项目的容器/孤儿与临时网络。
- PostgreSQL 与 Redis 命名卷保留；不发生 `--volumes`、镜像删除、prune、schema 操作或 seed 操作。
- Grafana 的 `/var/lib/grafana` 为 tmpfs，因此状态会重建且不留下匿名卷；仪表盘/数据源不是 SF02 资产。
- 第二次调用返回 0 并报告 `already stopped`，且不触碰其他工作区。
- `already stopped` 表示不存在精确项目容器或网络；失败启动留下的已停止容器仍会被移除。
- 即使 `.env.local` 被临时移走，命令仍成功，因为身份与 down 不依赖密钥。

若曾移走 `.env.local` 请恢复，并再次运行 `make dev`。自动化持久化验收证据会向 PostgreSQL 插入标记、循环 start/down 十次并验证 100% 保留；也会清理 Redis 夹具内容并证明正确性不变。

## 9. 校验安全的端口冲突失败

在 SF02 环境已停止时，用一次性终端占用配置的 Grafana 端口：

```bash
python3 -m http.server 3000 --bind 127.0.0.1
```

在另一终端：

```bash
make dev
```

预期：

- 非零退出的 `PORT_CONFLICT` 在创建新项目资源前点名 `grafana` 与端口 `3000`。
- 工作流不向无关 HTTP 服务发送 Grafana 凭据/请求，也永不停止它。
- 本干净启动场景下不会部分创建 PostgreSQL/Redis。

停止一次性 HTTP 服务后重跑 `make dev`；应正常收敛。

## 10. 校验负面与恢复测试套件

运行仓库测试，而不是把真实不安全值放进本工作区：

```bash
make test
```

预期 SF02 覆盖包括：

- 缺失/占位/畸形配置、非回环 URL、重复/非法端口，以及非 local 模式；
- 在状态变更前的 Docker/Compose/daemon/平台/远程 context 失败；
- 镜像拉取/digest/平台不匹配且就绪检查计时未开始；
- PostgreSQL 查询/认证、Redis 认证/PING 与 Grafana health/admin 失败；
- 陈旧健康、已停止容器、部分启动、daemon 丢失、命令中断与直接重试；
- 锁争用、安全锁路径 symlink/所有者/模式拒绝、重复启动、start 与 down 冲突、异常锁持有者退出与端口绑定竞态；
- Unicode/空格/symlink 路径、同路径稳定身份、不同 clone/worktree 隔离、短哈希碰撞失败与移动检测；
- 已提交 Compose 字节/stdin 传输、安全 runtime 项目目录、脏/symlink Compose 资产拒绝，以及一切自定义与 Compose 规范标签中无原始/规范化工作区路径；
- 本地密钥语法/配置注入拒绝，以及跨纯文本、JSONL、子进程环境、Compose/inspect 错误与测试的脱敏；
- environment-source 密钥 UID/GID/mode 检查、非 root PID 1 检查、Grafana tmpfs 与零匿名卷；
- 脏已跟踪与未跟踪工作区快照，证明 dev/dev-down 不改任何工作区文件；
- `NO_COLOR`、纯文本、非交互与屏幕阅读器终端输出回归；
- 仅处置带测试标签的 Compose 项目的可丢弃夹具清理，永不指向开发者项目资源。

测试目标可仅创建带动态回环端口与合成数据的隔离测试标签 Compose 项目。不得停止或删除第 3–8 节中的开发者环境。

## 11. 平台验收矩阵

通过同一已提交的确定性性能 harness 在代表性主机上执行第 1–10 节，并保留独立计时摘要。对 SC-001，每台主机执行一批预先声明的 20 次合法冷启动：计时前镜像已存在并校验，每次试验以无项目容器/网络且全新隔离的测试自有卷开始，至少 19/20 须在 60 秒内使三个依赖全部就绪。统计每一次合法试验；前置/工具链失败会使整批作废并重跑，而不是丢掉单个偏慢结果。

| 主机 | 容器变体 | 必需验收证据 |
|------|-------------------|-------------------|
| macOS arm64 | `linux/arm64` native | 路径/NFC 身份、Desktop 回环转发、健康、优雅停止、95% ≤60s 且重复 ≤15s |
| Linux x86_64 | `linux/amd64` native | Unix socket 权限、回环发布、健康、优雅停止、95% ≤60s 且重复 ≤15s |

公共 Make 目标、配置字段、项目 ID、服务名、健康规则、事件 schema、持久化语义与通过/失败行为必须一致。不得在 macOS arm64 上强制 `linux/amd64`。

对 SC-008，仓库工作流负责人按已提交的参与者标准与验收证据模板招募 10 名无 SF02 使用经验的代表性开发者。从前置已就绪的 checkout 起计时，每人仅使用根帮助与本地环境文档；至少 9/10 须在 10 分钟内独立完成配置准备、启动、确认三个依赖状态，并定位一条注入故障的恢复说明。仅记录汇总计时/结果与安全观察。

## 12. 审查验收证据

中心索引（已脱敏）：`specs/002-local-dependency-lifecycle/evidence/README.md`。

仅附带已脱敏产物：

- `make help` 与工具链能力结果（`evidence/quality-gates.md`）。
- 每平台 20 次冷启动摘要（至少 19/20 在 60 秒内，镜像计时除外），外加十次健康重复计时（`evidence/linux-amd64.md`、`evidence/macos-arm64.md`）。
- 逐依赖最终记录，对照 workflow event v2 标准信封校验，以及 v1 Make/event 不可变与消费者迁移验收证据。
- 十次 start/down/restart 循环，PostgreSQL 标记保留与稳定资源计数。
- API/Billing 200/503/恢复契约结果。
- 端口冲突、非法配置、认证失败、超时、锁冲突、工作区移动与远程 context 结果。
- Linux x86_64 与 macOS arm64 性能摘要。
- 十人新开发者验收汇总，至少 9/10 在 10 分钟内（`evidence/developer-usability.md`）。
- 两架构的镜像 tag/index/child digest、许可证评审与扫描（ADR 002 + `ops/workflow/local-dependencies.json`）。
- `git status --short` 证明未跟踪 runtime 配置、密钥、生成 override 或无关工作区变更。

不得附带 `.env.local`、原始 Compose config/inspect 输出、子进程环境/密钥内容、含 user-info 的 URL，或依赖异常正文。

### 激活状态（当前分支）

**T074 已完成（2026-07-25）**：公共 `make dev` / `make dev-down` 已激活，运行真实 SF02 生命周期；默认事件信封为 event v2。本 quickstart 第 3–8 节可直接对公共入口执行。历史诊断码 `SF02_NOT_READY` 曾用于激活前公共门禁，现不再是正常启动主路径；相关双平台与质量验收证据见 `evidence/README.md`（T068–T073 通过后完成激活）。
