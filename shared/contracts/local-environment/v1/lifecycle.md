# 契约：本地依赖环境生命周期

**版本**: 1.0.0
**所有者**: 仓库与基础设施维护者
**读者**: TokenMarket 开发者、API/Billing 服务维护者，以及工作流测试适配器

## 公共调用

根 Makefile 仍是唯一公共入口：

```text
make dev [mode=local]
make dev-down [mode=local]
```

省略 mode 与显式命令行 `mode=local` 均可接受。任何试图选择 test/prod 的其他取值或来源，均在访问 `.env.local`、Docker 配置、DNS、socket、镜像或资源之前以 `INVALID_MODE` 失败。`.env.local` 必须包含 `MODE=local`，但它永不选择或提升有效 mode。

成功为退出状态 0；任一失败为非零。精确的非零取值不保证稳定。`make dev` 与 `make dev-down` 仅替换 SF01 的 `SF02_NOT_READY` 过渡；其名称与根入口地位不改变。

该成功/副作用变更激活 Root Make Workflow v2，因此是破坏性的，即使目标名称保持稳定。契约优先的弃用与消费者迁移门禁定义于 [`make-workflow-v2.md`](./make-workflow-v2.md)。纯 action/mode 校验与已文档化的只读前置检查先于锁文件创建。前置检查一旦成功，锁争用优先于锁内再校验与变更诊断。

## 必需依赖集

恰好管理三个服务：

| 依赖 | 容器 DNS | 主机 URL 来源 | 默认主机端点 | 容器端口 | 持久化 |
|------------|---------------|-----------------|-----------------------|----------------|-------------|
| PostgreSQL 15 | `postgres` | `DATABASE_URL` | `127.0.0.1:5432` | 5432 | 项目命名卷；持久化本地事实 |
| Redis 7 | `redis` | `REDIS_URL` | `127.0.0.1:6379` | 6379 | 项目命名卷；保留但可重建 |
| Grafana OSS | `grafana` | `GRAFANA_URL` | `127.0.0.1:3000` | 3000 | 显式 `/var/lib/grafana` tmpfs；无匿名/命名卷 |

Kafka/Redpanda、Prometheus、Loki、MinIO、frontend、gateway 与 Python 服务均不启动，且不得影响生命周期成功。

定义来自经 [`local-dependency-manifest.schema.json`](./local-dependency-manifest.schema.json) 校验的运行时清单。仅有精确官方镜像 tag 而无其已评审多平台 OCI index digest 的定义无效。

## 配置契约

`make dev` 恰好读取一个被忽略文件：仓库根目录 `.env.local`。Shell/环境变量值不覆盖生命周期字段。

```text
MODE=local
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:<port>/<database>
REDIS_URL=redis://default:<password>@127.0.0.1:<port>/<db-number>
GRAFANA_URL=http://127.0.0.1:<port>
GRAFANA_ADMIN_PASSWORD=<synthetic-local-secret>
```

规则：

- 每个解码后的本地密钥匹配 `^tm_local_[A-Za-z0-9_-]{32,96}$`。百分号编码仅在解码结果符合该语法时接受。空白、引号、反斜杠、分隔符、控制字符、CR/LF 与 NUL 均被拒绝，从而使 Redis 配置生成无法新增指令。
- SF02 仅接受 IPv4 字面量 `127.0.0.1`。不接受通配、主机名、局域网、生产、测试、IPv6 或远程地址。
- PostgreSQL 用户/密码/库与 Redis 默认用户密码/数据库编号为必填。
- Grafana URL 不含 user-info；其管理员密码为独立字段。管理员用户名为已提交的非密钥常量 `admin`。
- URL 查询串/fragment 被拒绝；Grafana 路径仅可为空或 `/`。
- 端口为 1–65535 且两两不同。主机端口覆盖仅可通过修改其 URL 完成。
- `.env.example` 值为不可用占位符。空值、不符合确定性 `tm_local_` 语法的值、类似提供商密钥的值与非本地地址失败关闭（fail-closed）；工作流不声称能识别所有真实世界生产密钥。
- 校验消息包含字段名与恢复方向，不包含所提供的值。

工作流在内存中通过将 host/port 替换为规范服务名/容器端口推导容器 URL。它可以推导专用子进程变量与固定容器密钥文件目标，但这些不是用户配置，且不得覆盖 URL 事实源。

`make dev-down` 不要求、不解析、不校验 `.env.local`。

## 工作区身份与所有权

```text
canonical_path = NFC(physical_resolved_repository_root_without_trailing_separator)
workspace_hash = first_12_lower_hex(SHA256(UTF8(canonical_path)))
workspace_fingerprint = all_64_lower_hex(SHA256(UTF8(canonical_path)))
project_id     = "tokenmarket-" + workspace_hash
```

规范路径永不输出或存储到资源元数据。分支名与配置密钥不是输入。

每个 Compose 命令显式提供项目 ID，以及每用户运行时基目录下安全的 `0700` 项目目录。该目录仅由 `project_id` 推导；不是仓库根。适配器验证 `infra/docker/compose.local.yml` 为常规非 symlink 文件，且其字节等于已提交 Git blob，再经 stdin 以 `-f -` 提供这些字节。因此仓库路径既不出现在 Compose 参数中，也不出现在 Compose 规范的工作目录/配置文件标签中。脏或被替换的 Compose 资产在访问 Compose 前失败关闭。Compose 项目作用域拥有容器、默认网络与命名卷。资源携带：

```text
com.tokenmarket.repository=tokenmarket
com.tokenmarket.workspace-id=<project_id>
com.tokenmarket.workspace-fingerprint=<workspace_fingerprint>
```

精确项目 ID 加全指纹是变更边界。匹配 12 位十六进制项目 ID 但全指纹不同，视为检测到的哈希碰撞，并在变更前以 `RESOURCE_OWNERSHIP_CONFLICT` 失败。前缀/标签发现必须报告不同的旧工作区 ID 并给出恢复方向，但永不接管、停止、移除、重命名或挂接其资源。工作区移动按设计创建新的项目 ID。

## 运行时与平台前置检查

受支持主机：

- 带本地 Docker Desktop Linux 容器的 macOS arm64
- 带本地 Docker Engine 的 Linux x86_64

已评审工具链为 Docker 29.5.3 与 Compose 5.1.4。在依赖配置的资源访问之前，工作流验证：

1. Docker CLI 与 Compose 存在且匹配维护版本。
2. daemon 可到达，并在期望架构上运行 Linux 容器。
3. 所需 Compose 选项/JSON 输出存在；维护版本契约夹具已证明 environment-source 密钥 `uid`/`gid`/`mode` 语义，因此每轮前置检查不创建探针容器。
4. 活动端点为本地 Unix socket。`tcp://`、`ssh://`、远程 context 与远程 `DOCKER_HOST` 均被拒绝。

工作流永不安装/升级 Docker、更改 socket 权限/组、调用 `sudo`，或更改 daemon 配置。

## 锁契约

每个项目 ID 存在一把非阻塞排他的 POSIX 咨询锁（advisory lock）文件锁。在 macOS 上基目录为操作系统提供的每用户临时目录；在 Linux 上为有效时的已拥有 `/run/user/<euid>` 目录，否则为 root 拥有且 sticky 的 `/tmp` 下已拥有的 `0700` 子目录。其下，仅由 `project_id` 命名的当前用户 `0700` 目录包含锁与空的 Compose 项目目录。每个路径分量在不跟随 symlink 的情况下检查；锁文件为当前用户拥有的常规 `0600` 文件，以 `O_NOFOLLOW|O_CREAT` 打开。所有权、模式或类型漂移失败关闭。其中不存储密钥或原始工作区路径。

对 `dev`，纯 action/mode、清单/运行时、`.env.local`、只读项目检查与无凭据端口前置检查发生在锁文件创建之前，使非法请求甚至无法修改协调元数据。随后在第一次可变动作之前立即获取项目锁；在锁内再校验运行时端点、所有权与端口状态，以关闭前置检查竞态。锁在镜像拉取、状态协调（reconcile）、就绪检查、最终状态与最终事件发出期间保持持有。`dev-down` 无密钥/配置前置检查，并在身份计算之后立即获取锁。

若锁被持有：

- 第二次操作发出 `OPERATION_IN_PROGRESS`；
- 立即返回非零；
- 不创建、启动、停止、探测或删除任何内容；
- 调用方可在活动操作结束后重试。

内核在进程正常或异常退出时释放锁。仅锁文件存在并不表示操作处于活动状态。

## `make dev` 有序契约

1. 在不读取 `.env.local`、Docker、socket 或锁状态的情况下校验 action 语法与有效 local mode。
2. 计算身份；只读校验清单、Docker/Compose/本地端点、受支持主机与运行时能力。
3. 读取并校验 `.env.local`；仅在工作流内存中推导三个密钥 payload。
4. 只读检查精确项目身份/指纹/状态/发布者，并执行无凭据端口前置检查。
5. 获取安全项目锁，创建/校验其旁路安全 Compose 项目目录，再校验本地端点、所有权/状态与端口。任一漂移在拉取或项目变更前失败。
6. 对再校验后每个期望端口：
   - 接受匹配服务、绑定地址与端口的精确项目发布者；
   - 否则在不发送协议数据的情况下测试本地绑定可用性；
   - 若不可用，在创建前以 `PORT_CONFLICT` 失败。
7. 仅拉取缺失的已提交镜像 digest。按依赖发出拉取结果与耗时。
8. 在本地校验每个镜像 digest 与原生目标平台 manifest。
9. 启动一个新的单调 60 秒就绪检查截止时间。
10. 使用经 `-f -` 的已验证已提交 Compose 字节、安全运行时项目目录与 `up --detach --pull never` 进行状态协调；Compose 执行消耗同一截止时间，若无剩余时间则被终止/归类。
11. 轮询当前每服务 JSON 状态，并并发运行三个依赖特定的认证探针。每次尝试受当前剩余时间约束；重试在共享截止时间停止。Compose healthcheck 使用相同认证语义作为补充验收证据，但永不延长或替换工作流截止时间。
12. 仅当三者均在该截止时间前具备即时验收证据时，发出逐依赖最终结果并聚合成功。截止后的探针不得使运行变为成功。

健康的重复启动不新增容器、网络或卷，且必须在 15 秒内完成。它不接触 registry，也不重写配置/锁。

资源创建后的失败保留可检查的项目状态与全部卷。工作流不自动 down、回滚、删除卷、迁移、seed 或重置。正常的精确拥有状态协调可替换镜像不同于已验证期望 digest 的容器，但保留其声明的命名卷。修复所报告原因并重跑必须能安全收敛。

## 就绪检查契约

| 依赖 | Liveness 证据 | 最终就绪检查证据 |
|------------|-------------------|--------------------------|
| PostgreSQL | 容器进程加 TCP 服务器状态 | 配置的用户/密码/库经 TCP 认证，且 `SELECT 1` 恰好返回 `1` |
| Redis | 容器进程在协议层响应 | 默认用户以 URL 密码认证，且同一连接对 `PING` 返回 `PONG` |
| Grafana | `GET /api/health` 返回 200 | Health JSON 含 `database=ok`；Basic Auth `GET /api/user` 返回 200 且 `isGrafanaAdmin=true` |

仅容器 `running`、开放 TCP 端口、`pg_isready`、未认证 Redis 可达、Grafana 首页或陈旧健康本身均不足。状态协调调用、状态轮询与并发调度的探针共享同一整体 60 秒就绪检查截止时间。仅发出安全类别，而非原始探针输出。

## 密钥传输与输出

- 解析后的密钥仅存在于 Compose 调用的专用子进程环境映射中；该映射永不合并入父环境、打印、在异常中返回或在调用后保留。
- Compose 顶层密钥使用 `environment` 源与每服务长语法。已评审清单提供每个已验证非 root 运行时 UID/GID 与 mode `0400`；与 file-source 密钥不同，该传输在容器内应用所有权/模式，并避免主机绑定权限不匹配。
- PostgreSQL 通过其挂载密钥使用 `POSTGRES_PASSWORD_FILE`。
- Redis 从挂载的 `0400` 密钥 `redis.conf` 启动，其中恰好包含一条 `requirepass tm_local_...` 指令；密码不是进程参数，且严格语法使引用/配置注入不可能。
- Grafana 使用 `GF_SECURITY_ADMIN_PASSWORD__FILE`。
- Redis 客户端探针使用短生命周期 `REDISCLI_AUTH` 子进程环境，永不使用 `redis-cli -a`。
- Compose config 输出、inspect health 输出、HTTP 正文、含 user-info 的 URL、子进程环境映射与命令异常仅内部使用，并在归类前始终脱敏。
- 每条 JSONL 记录为标准事件封装，带有唯一 UUID `event_id`、稳定 `event_type=workflow.step`、`schema_version=2.0.0`、UTC RFC 3339 `timestamp`、`producer=repository-workflow`，以及生命周期运行级 `correlation_id`。其严格 `payload` 包含 action、component、phase、status、code、duration 与安全 message；依赖作用域阶段包含 `dependency`，而聚合 identity/final payload 可省略之。
- 纯文本记录表达相同的安全 payload 语义与关联 ID。两种形式均不依赖颜色、图标、动画或交互终端行为。

## `make dev-down` 有序契约

1. 校验 action/mode，然后计算身份并获取同一项目锁，不读取配置。
2. 仅校验定位精确项目所需的本地运行时事实。
3. 发现精确项目资源，并扫描仓库标签中的工作区移动资源。不同工作区 ID 为强制仅报告发现，并给出恢复方向。
4. 若不存在精确项目容器或网络（保留的命名卷可以存在），返回成功（`already stopped`）。已停止容器或孤儿网络仍需状态协调。
5. 从同一经 stdin 的已验证已提交 Compose 字节、安全运行时项目目录与安全 `tm_local_` 仅解析密钥值，执行精确项目的 `down --remove-orphans`，且无 CLI 超时覆盖、`--volumes`、`--rmi` 或 prune。因此 Compose 使用声明的每服务优雅期：PostgreSQL 60 秒，Redis/Grafana 30 秒。工作流子进程/状态校验截止时间为 75 秒。
6. 确认精确项目容器与临时网络已不存在；确认命名卷仍保留。
7. 丢弃仅解析子进程环境，并在最终事件后释放锁。

若 Compose 无法为 down 解析，回退可以仅停止/移除其 Compose 项目标签恰好等于计算出的项目 ID 与全指纹的容器与网络。它永不触碰卷或前缀匹配资源。stop 超时/强制终止为失败证据，而非静默成功。

## 数据语义

- PostgreSQL 命名卷在 down/up、重试、部分失败、命令中断与主机重启间保留。
- Redis 命名卷亦由普通 down 保留，但 Redis 内容从不是持久化事实，全部行为必须能从空内容恢复。
- Grafana `/var/lib/grafana` 为显式 0700 tmpfs，由已验证运行时 UID/GID 拥有，从而使镜像无需 root 即可写入，且不能创建匿名数据卷。状态在 SF02 中为临时；数据源、仪表盘与告警由 SF19 拥有。
- Start/down 永不运行 Alembic、初始化业务 schema、seed 数据、轮换既有 PostgreSQL 角色密码，或复制生产数据。
- SF02 不暴露破坏性清理目标。未来清理动作需要单独契约、影响说明与强确认。

## 稳定诊断

| 错误码 | 含义 | 副作用边界/恢复 |
|------|---------|-------------------------------|
| `INVALID_MODE` | 非 local 或不安全 mode 来源 | 在配置/资源访问前；以 local 重试 |
| `INVALID_CONFIG` | 缺失/非法/占位/非本地字段 | 在创建前；修复所命名字段 |
| `TOOL_MISSING` | Docker 或 Compose 缺失 | 在资源变更前；在外部安装已评审工具 |
| `TOOL_VERSION_UNSUPPORTED` | 运行时/版本/平台/能力不受支持 | 在资源变更前；使用维护中的运行时 |
| `IMAGE_UNAVAILABLE` | 拉取、digest、平台、磁盘或身份校验失败 | 在容器创建前；修复 registry/磁盘/manifest |
| `PORT_CONFLICT` | 期望回环端口被他方占用或绑定竞态丢失 | 永不停止占用者；释放端口/修改 URL 后重试 |
| `DEPENDENCY_NOT_READY` | 认证就绪检查失败或超时 | 项目状态保留；检查安全诊断/修复/重试 |
| `OPERATION_IN_PROGRESS` | 每项目锁被持有 | 无副作用；稍后重试 |
| `RESOURCE_OWNERSHIP_CONFLICT` | 精确名称/项目资源与所拥有身份不匹配 | 不接管/删除；遵循恢复指南 |
| `STEP_FAILED` | 意外的有界 Compose/stop 失败 | 状态保留；检查并重试 |

`SF02_NOT_READY` 仍保留为历史 SF01 过渡验收证据，但已实现的 `dev`/`dev-down` 不再发出该码。

全部诊断由本地 CLI 同步检测，严重性为 **本地阻塞 / 无自动 page**：未监控共享生产服务，因此 page 会造成误导。仓库工作流维护者拥有 mode/锁/事件失败；基础设施维护者拥有 Docker/镜像/端口/资源/Compose 失败；API/Billing 所有者拥有其服务就绪检查失败。每个错误码链接到 `ops/runbooks/local-environment.md`；缺少该所有者/恢复映射的实现无法通过契约检查。

## API/Billing 消费者契约

SF02 不启动业务服务。当 API Service 或 Billing Service 被独立启动时：

- `/health/live` 永不探测 PostgreSQL，且在 PostgreSQL 不可用时仍保持可用。
- `/health/ready` 执行独立拥有、两秒有界的 async `SELECT 1` 探针。
- Ready 返回既有 200 响应形状。
- 非法配置、连接、认证、超时或查询失败返回 [`service-health-v1.1.openapi.yaml`](./service-health-v1.1.openapi.yaml) 中的 503 形状。
- 探针失败按即时评估；恢复可在不重启服务的情况下回到 200。
- Gateway、Admin Service、Redis、Kafka 与提供商在 SF02 中不作为就绪检查依赖加入。

## 兼容性与变更控制

- 公共目标重命名/移除、普通 down 时删除卷、更大的依赖集、非 local mode、远程 Docker context 或非回环发布均为破坏性变更。
- 主机 URL 语法、规范服务名、项目哈希规则、镜像身份、就绪检查探针、持久化等级、事件字段/错误码与 stop 语义为已评审契约。
- 根目标语义与事件变更遵循 [`make-workflow-v2.md`](./make-workflow-v2.md) 与 [`workflow-event-v2.0.schema.json`](./workflow-event-v2.0.schema.json)。健康变更遵循 OpenAPI 契约。
- 依赖发布/digest 变更须同时更新运行时清单、扫描/许可证验收证据、ADR 引用、双平台校验与回滚身份。
