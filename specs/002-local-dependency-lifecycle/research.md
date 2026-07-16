# Research: 本地依赖环境生命周期

**Feature**: `002-local-dependency-lifecycle`
**Date**: 2026-07-15
**Status**: Complete — no unresolved `NEEDS CLARIFICATION`

## Decision 1: 以现有 Python 工作流工具作为生命周期适配器

**Decision**: 保留根 `Makefile` 的 `make dev`、`make dev-down` 作为唯一公开入口，在 `tools/workflow/` 增加一个有明确边界的本地环境模块，并由 `workflow.cli.execute_action()` 在现有组件聚合逻辑之前分派。模块分为纯函数领域层（配置、工作区身份、状态与诊断映射）和可替换的 Docker Compose 进程适配器。`infra/docker/compose.local.yml` 只描述 PostgreSQL、Redis、Grafana 及其网络、卷、健康检查；不新增公开脚本或第二套 CLI。

**Rationale**: SF01 已经拥有参数来源校验、可解析事件、脱敏、工具链检查和根入口。扩展该实现可保持公开目标、退出语义和输出契约，并允许单元测试使用伪 Compose 适配器，真实集成测试再连接 Docker。

**Alternatives considered**:

- 让 Makefile 直接拼接 Compose 命令：会复制校验、锁、脱敏和事件逻辑，难以测试竞态。
- 新增 shell 脚本或独立 CLI：形成第二公开工作流，违反 SF01 与仓库规范。
- 引入 Docker SDK for Python：增加锁依赖和 API 兼容面；当前只需要受约束的官方 CLI JSON 输出。

## Decision 2: 使用单一 Compose 应用和显式项目身份

**Decision**: 所有生命周期调用都显式传入 `--project-name tokenmarket-<workspace_hash>`、`--project-directory <secure-runtime-base>/<project-id>/compose-project`、`-f -` 和 `--ansi never`。适配器先确认 `infra/docker/compose.local.yml` 是普通非 symlink 文件且字节与已提交 Git blob 完全一致，再把这些已验证字节经 stdin 交给 Compose；仓库绝对路径不进入 Compose 参数或模型。安全 project directory 只含 project id，由当前用户以 `0700` 创建并逐级拒绝 symlink。容器、默认网络和 named volumes 使用 Compose project scope，并附加不含路径的 `com.tokenmarket.repository`、`com.tokenmarket.workspace-id` 及完整 64-hex `com.tokenmarket.workspace-fingerprint` 标签；12-hex 相同但完整 fingerprint 不同视为碰撞并失败关闭。不使用 Compose 顶层 `name`、目录 basename、Git 分支、`COMPOSE_PROJECT_NAME`、固定 `container_name` 或全局自定义 volume name。

**Rationale**: Compose 将 project name 作为同一应用多部署实例的隔离边界，`-p/--project-name` 优先级最高；Compose 自动写入 project/service 标签。Compose v5 API 还定义了保存绝对 working directory/config file 的规范标签，因此把仓库目录直接用作 project directory 或 `-f` 路径会违反 FR-016。stdin 配置加只含哈希身份的安全 runtime directory 消除了调用者当前目录影响，并使 Compose 规范标签也不含原始工作区路径；真实集成测试必须扫描全部标签验证这一点。[Compose project name](https://docs.docker.com/compose/how-tos/project-name/)、[Compose CLI](https://docs.docker.com/reference/cli/docker/compose/)、[Compose application model](https://docs.docker.com/compose/intro/compose-application-model/)、[Compose v5.1.4 API labels](https://pkg.go.dev/github.com/docker/compose/v5@v5.1.4/pkg/api)

**Alternatives considered**:

- 目录名或分支名：不同 clone/worktree 会碰撞，切换分支会改变所有权。
- 自定义固定资源名：绕过 project scope，可能跨工作区命中。
- 直接传仓库目录与 Compose 文件路径：Compose 的规范 working-dir/config-files 标签会持久化绝对路径。
- 按仓库前缀批量停止：发现标签不是授权边界，只允许用于只读提示旧资源。

## Decision 3: 精确且多架构地固定三项镜像

**Decision**: 依赖版本选择为 PostgreSQL `15.18-bookworm`、Redis `7.2.14-bookworm` 和 Grafana OSS `13.0.3`。运行时事实清单必须把每项写成“可读精确标签 + 同时包含 `linux/amd64`、`linux/arm64` 的 OCI index digest + 两个平台 child digest”；Compose 只能消费 `repository:tag@sha256:index`，适配器还要把当前平台实际 image identity 与相应 child digest 对照。实施时必须从官方/Verified Publisher registry 解析真实 index 与两平台 child digest、扫描并提交，不能把占位 digest 合入。Redis 选择 7.2 系列以保持 BSD-3-Clause 许可边界；升级到 7.4+ 必须单独评审许可和安全影响。Grafana 使用 `grafana/grafana`，不使用已停止更新的 `grafana/grafana-oss`。

**Rationale**: tag 可重新指向，digest 才是不可变发布物；multi-platform index 让同一契约在 Apple Silicon 和 Linux x86_64 上选择原生变体。PostgreSQL 15 满足 SF02/SF01 主版本契约，所选补丁版本包含截至计划日期的维护修复。[Docker digests](https://docs.docker.com/dhi/core-concepts/digests/)、[multi-platform images](https://docs.docker.com/build/building/multi-platform/)、[PostgreSQL official image](https://hub.docker.com/_/postgres/)、[Redis official image](https://hub.docker.com/_/redis)、[Grafana Docker install](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/)

**Alternatives considered**:

- `15`、`7` 或 `latest`：浮动且不可审计。
- 只有精确 tag：仍可被 registry 重新发布。
- 每个平台维护 child digest/Compose 文件：形成两套行为并增加漂移。
- Redis 7.4：当前没有所需特性，且增加 RSALv2/SSPLv1 许可评审。

## Decision 4: 镜像获取与 60 秒 readiness 分阶段

**Decision**: 在任何容器创建前执行 `docker compose pull --policy missing`，然后检查声明的三个 index/child digest 都已存在且平台匹配。只有此阶段成功后才启动单一 60 秒 monotonic deadline，执行 `docker compose up --detach --pull never`，并在剩余预算内并发轮询当前 Compose JSON 状态和三项认证探测。Compose 调用、状态采集、每次短探测及重试共享同一 deadline；deadline 后不得补探测并改判成功。镜像获取和 readiness 分别产生事件与耗时；健康环境不访问 registry。超时保留容器、网络和卷供诊断，不自动 `down`。

**Rationale**: Compose 支持 digest image、`pull_policy`、`pull --policy` 和 detached reconcile。`pull missing` 满足首次自动获取，`up --pull never` 保证 readiness 阶段不偷偷访问 registry 或改变身份。若先给 `up --wait` 完整 60 秒再做最终认证探测，总预算必然可能越界，因此由适配器拥有一个权威 deadline。[Compose image/pull policy](https://docs.docker.com/reference/compose-file/services/#pull_policy)、[docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/)

**Alternatives considered**:

- 每次 `always` pull：破坏 15 秒重复确认目标并引入网络依赖。
- `never` pull：不能满足缺失镜像自动获取。
- 把 pull 计入 60 秒：与澄清答案及可诊断性冲突。

## Decision 5: 工作区身份使用规范路径的 SHA-256 短哈希

**Decision**: 工作流从自身位置确定仓库根，对根路径执行物理解析（解析 `.`、`..` 和 symlink）、移除非根尾分隔符、以 Unicode NFC 规范化，并按 UTF-8 编码。`workspace_hash = sha256(canonical_path_bytes).hexdigest()[:12]`，`project_id = tokenmarket-<workspace_hash>`。不做大小写折叠，不包含分支或秘密。原始/规范路径都不得进入资源名、标签、事件或日志。

**Rationale**: 规则在 macOS arm64 与 Linux x86_64 上可由 Python 3.11 标准库确定地实现；同一路径跨重启/分支稳定，不同 clone/worktree 极低概率碰撞。保留大小写避免在大小写敏感 Linux 文件系统上错误合并两个合法路径。

**Alternatives considered**:

- Git remote/仓库名：多个 worktree 共享，不能隔离。
- 分支名：切换分支会失去资源所有权。
- 把路径直接放进标签：泄露开发者目录和用户名。
- 机器随机 UUID：不可从缺失配置中重新计算，`dev-down` 无法恢复。

## Decision 6: URL 是唯一连接事实源，并采用严格本地语法

**Decision**: `make dev` 先确认 Make 参数的有效模式只能是 omitted/local，再读取仓库根的被忽略 `.env.local` 并要求文件内 `MODE=local`。生命周期字段只从该文件读取；shell 不可覆盖 URL 或秘密。所有解码后秘密必须匹配 `^tm_local_[A-Za-z0-9_-]{32,96}$`，从而可判定为本地合成值并排除 Redis 配置注入字符。严格语法为：

- `DATABASE_URL`: `postgresql://<user>:<percent-encoded-password>@127.0.0.1:<port>/<database>`；用户、密码和数据库均非空，不允许 query/fragment。
- `REDIS_URL`: `redis://default:<percent-encoded-password>@127.0.0.1:<port>/<db-number>`；密码必需，数据库号是非负整数，不允许 query/fragment。
- `GRAFANA_URL`: `http://127.0.0.1:<port>`；不得包含 user-info、query/fragment 或非根路径。
- `GRAFANA_ADMIN_PASSWORD`: 独立非空合成本地秘密；固定非秘密管理员名为 `admin`。

端口为 1–65535 且三项互不相同；示例默认 5432、6379、3000。只接受 IPv4 literal `127.0.0.1`，避免 `localhost`/IPv6 解析在两平台产生隐式差异。容器地址通过只替换 host 为 `postgres`、`redis`、`grafana` 派生；Compose 所需的用户名、密码文件、数据库和 published port 是运行时派生值，不是第二配置入口。校验错误只输出字段名和稳定代码。

**Rationale**: 单一 URL 事实源消除独立 host/port 变量漂移；严格 loopback literal 可证明端口不会默认发布到 `0.0.0.0`。[Compose ports](https://docs.docker.com/reference/compose-file/services/#ports)、[Docker port publishing](https://docs.docker.com/engine/network/port-publishing/)

**Alternatives considered**:

- 接受独立 `POSTGRES_PORT` 等变量：产生竞争事实源。
- 接受任意 loopback 名称/IPv6：需要双栈映射和更多平台契约，SF02 无需扩大。
- 接受 process env 覆盖：容易把生产 shell 配置误注入本地生命周期。

## Decision 7: 使用 Compose environment-source secret file bridge

**Decision**: 生命周期把已验证密码放入仅传给单次 Compose 子进程的专用 environment mapping；Compose 顶层 `secrets` 使用 `environment` source，并用 service long syntax 把秘密以 `0400` 文件挂载给清单中验证过的上游非 root UID/GID。PostgreSQL 使用 `POSTGRES_PASSWORD_FILE`，Grafana 使用 `GF_SECURITY_ADMIN_PASSWORD__FILE`，Redis secret 内容是严格生成且仅含一个 `requirepass tm_local_...` 指令的 `redis.conf`。命令参数、Compose YAML、容器 environment/argv、事件和错误都不含值。子进程结束后 mapping 不再保留。

`dev-down` 不校验或读取 `.env.local`，只给 Compose 子进程传入符合语法但无真实意义的 parse-only secret 值。若标准 `down` 无法解析，fallback 只能依据精确 project id、完整 fingerprint 和 Compose project labels 处理容器/网络，绝不按仓库前缀批量操作或删除卷。

**Rationale**: Compose 对 file-source secret 使用 bind mount，会忽略 `uid/gid/mode`，这与宿主 0600 文件和非 root 容器不兼容；官方文档明确说明 environment-source secret 才实现这些容器内属性。该桥接仍把秘密作为文件交给服务而不写入 worktree、host runtime file、container env 或 argv。PostgreSQL 与 Grafana 支持 file-based secret，Redis 配置文件避免密码进入 argv。[Compose service secrets](https://docs.docker.com/reference/compose-file/services/#secrets)、[PostgreSQL official image](https://hub.docker.com/_/postgres/)、[Grafana Docker configuration](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/)、[Redis CLI](https://redis.io/docs/latest/develop/tools/cli/)

**Alternatives considered**:

- 把值放入 service `environment` 或 `command` 插值：值会进入 inspect 或进程参数；只有 top-level secret 的 environment source 被采用。
- 在工作区或宿主 runtime 目录生成 bind-mounted 0600 文件：非 root image UID 无法跨平台稳定读取，且 file-source secret 的 ownership 属性会被忽略。
- 无 Redis 认证：不能验证认证失败场景，且隔离网络中的进程可直接访问。

## Decision 8: 每项目 POSIX advisory lock 串行化完整状态改变

**Decision**: `dev` 先完成纯 mode、manifest/runtime、配置、只读项目检查和无凭证端口预检，使非法输入在 lock inode 创建前失败；随后使用 Python `fcntl.flock(LOCK_EX | LOCK_NB)` 锁定确定的 per-user runtime base 中只含 project id 的 lock 文件，并在锁内重新验证 endpoint/ownership/ports 后才允许 pull 或资源改变。`dev-down` 无配置预检，identity 后立即取同一锁。macOS base 使用 OS per-user temp；Linux 优先验证 `/run/user/<euid>`，否则在 root-owned sticky `/tmp` 下安全创建 current-user `0700` 子目录。目录/文件逐级 `lstat/openat`、不跟随 symlink，lock 是 current-user regular `0600` file。锁覆盖所有 mutable action、健康采集和最终事件；未获锁立即 `OPERATION_IN_PROGRESS`，内核在进程退出时释放。

**Rationale**: Compose 的 parallel 控制只影响单进程内部 Engine 调用，不提供跨 `up`/`down` 进程互斥。`fcntl` 同时存在于受支持的 macOS 与 Linux，避免依赖 macOS 默认没有的 `flock(1)`。[Compose parallelism](https://docs.docker.com/reference/cli/docker/compose/#configuring-parallelism)

**Alternatives considered**:

- 只依赖 Compose 幂等：并发 up/down 仍有竞态。
- PID/lock directory：需要处理 stale、PID 复用和异常清理。
- 等待锁：隐藏操作实际排队状态，不符合明确可重试结果。

## Decision 9: 端口预检不访问无关服务

**Decision**: 先用精确 project id 的 `compose ps --all --format json` 判断端口是否已由本项目健康/可协调实例拥有。否则工作流只尝试在 `127.0.0.1:<port>` 建立临时监听以检查可绑定性，不向占用端口发送协议或凭证。占用在创建资源前报 `PORT_CONFLICT` 和依赖/端口。预检释放监听后的竞态由 Docker 实际 publish 结果兜底，并映射为同一诊断类别；绝不停止占用者。

**Rationale**: 连接未知服务可能泄露认证或产生副作用；bind 检查只回答端口所有权。Compose JSON 状态提供 Project、Service、Health 和 publishers，适合安全识别现有项目资源。[Compose ps JSON](https://docs.docker.com/reference/cli/docker/compose/ps/#format-the-output---format)

**Alternatives considered**:

- 仅 TCP connect：不能证明所有权，还可能把凭证发给错误实例。
- 发现冲突后自动重映射：会让文档、URL 与运行状态漂移。
- 停止冲突进程：超出授权范围。

## Decision 10: Compose health 与显式认证探测共同定义 readiness

**Decision**: 三个服务均声明与最终规则等价的 authenticated healthcheck 作为 Compose 状态证据；包装器在 `up --detach` 后按同一 deadline 并发采集逐依赖状态并执行安全认证探测，最终状态以实时 `ps/inspect` 加本次显式探测为准。PostgreSQL host query 在独立 workflow lock 中新增与服务对齐的 asyncpg 0.30.x；Redis RESP 与 Grafana HTTP 使用标准库，不依赖宿主 `psql`/`redis-cli`/`curl`：

- PostgreSQL：使用同一 URL 的用户、密码、数据库，经 TCP 认证后执行 `SELECT 1`，严格要求结果 `1`。`pg_isready` 只能做 liveness 辅助。
- Redis：使用 default user/URL 密码认证并在同一连接执行 `PING`，严格要求 `PONG`；探测进程用 `REDISCLI_AUTH`，不使用 `-a`。
- Grafana：无认证 `GET /api/health` 必须返回 200 且 `database == "ok"`；Basic Auth `GET /api/user` 必须返回 200 且 `isGrafanaAdmin == true`。

健康探测使用短间隔与单次短超时，并由 `remaining = deadline - monotonic_now` 截断，三项总体不超过 60 秒。任何原始 health output、HTTP body 或异常都不直接输出，只映射为稳定的脱敏原因。三项互不依赖，不使用 `depends_on`。`docker compose wait` 被排除，因为它等待容器停止而非健康。[Compose healthcheck](https://docs.docker.com/reference/compose-file/services/#healthcheck)、[PostgreSQL pg-isready](https://www.postgresql.org/docs/15/app-pg-isready.html)、[Redis AUTH/PING](https://redis.io/docs/latest/commands/auth/)、[Grafana Health API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/other/)、[Grafana User API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/user/)

**Alternatives considered**:

- running/TCP/`pg_isready`：不能证明目标认证、数据库和查询。
- 只依赖 Compose health：无法验证 Grafana 管理员身份，也缺少稳定的逐依赖诊断。
- 用业务表查询：耦合迁移并违反 SF02 不创建 Schema 的边界。

## Decision 11: PostgreSQL durable，Redis preserved-but-rebuildable，Grafana ephemeral

**Decision**: PostgreSQL 使用 project-scoped named volume 挂载 `/var/lib/postgresql/data`；Redis 使用 named volume 挂载 `/data`，普通停止保留但正确性不得依赖其内容；Grafana 显式以其验证 runtime UID/GID 拥有的 0700 tmpfs 覆盖 `/var/lib/grafana`，避免 root 运行与镜像声明产生匿名卷，数据源/看板继续属 SF19。普通停止执行 `down --remove-orphans`，不传 CLI timeout override，因而由 Compose 应用 PostgreSQL 60 秒、Redis/Grafana 30 秒的 service `stop_grace_period`；外围 75 秒 deadline 覆盖命令与验收。永不使用 `--volumes`、`--rmi`、prune 或匿名卷；强制终止必须成为失败证据。

**Rationale**: Compose `down` 默认保留 named volumes，`-v` 才删除；官方镜像规定 PostgreSQL 17 及以下和 Redis 的持久目录。Grafana `admin_password` 只在首次启动应用，持久 SQLite 会让秘密轮换与配置产生漂移，而 SF02 不拥有任何必须保留的 Grafana 业务资产。[Compose down](https://docs.docker.com/reference/cli/docker/compose/down/)、[Compose volumes](https://docs.docker.com/reference/compose-file/volumes/)、[PostgreSQL shutdown](https://www.postgresql.org/docs/15/server-shutdown.html)、[Grafana configuration](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/)

**Alternatives considered**:

- `docker compose stop`：不移除运行实例和临时网络。
- bind mounts：增加 macOS/Linux 文件共享、权限与 Unicode 路径差异。
- 持久 Grafana SQLite：SF02 无持久资产，却引入密码轮换问题。

## Decision 12: 只支持本地 Docker endpoint 和同一跨平台定义

**Decision**: 支持矩阵是 macOS arm64（Docker Desktop Linux VM）与 Linux x86_64（本地 Docker Engine），统一使用 Docker 29.5.3、Compose 5.1.4、同一 Compose 文件与多平台 index。预检验证 CLI/Compose 版本、daemon 可达、Linux container OS、目标架构、所需 flags/JSON 能力，以及当前 Docker endpoint 为本机 Unix socket；拒绝 `tcp://`、`ssh://`、远程 `DOCKER_HOST`/context。宿主访问只走 published loopback port，不能依赖 container IP、`docker0`、iptables 或 systemd。

**Rationale**: Docker Desktop 的容器运行在 VM 中，宿主不能依赖 Linux bridge IP；published port 是两平台共同稳定边界。远程 daemon 不共享本机 `fcntl` 锁，无法满足并发与端口所有权保证。Engine 29 也高于 Docker 对 28.0.0 以前 loopback publish 的安全警告范围。[Docker Desktop networking](https://docs.docker.com/desktop/features/networking/networking-how-tos/)、[Linux Docker post-install](https://docs.docker.com/engine/install/linux-postinstall/)、[port publishing](https://docs.docker.com/engine/network/port-publishing/)

**Alternatives considered**:

- 为两平台维护 override：形成第二契约并易漂移。
- 在 arm64 强制 amd64：进入模拟路径，破坏性能验收。
- 支持远程 context：锁、端口预检和秘密边界不成立。

## Decision 13: API/Billing readiness 使用注入式异步 PostgreSQL probe

**Decision**: API Service 与 Billing Service 各自拥有相同协议形状但不跨服务导入实现：应用 lifespan 创建 SQLAlchemy async engine（现有锁定依赖，`pool_pre_ping=True`），readiness probe 在 2 秒总超时内获取连接并执行 `SELECT 1`，不在单次 HTTP 请求内重试。`postgresql://` 配置在服务内部安全转换为 `postgresql+asyncpg://` 驱动，不改变认证/主机/数据库事实。shutdown dispose engine。测试通过 `app.state`/依赖注入替换 probe。

`/health/live` 永远不探测数据库。`/health/ready` 在成功时保留 SF01 的 200 响应形状；数据库配置、认证、连接或查询失败时返回 503、`status=not_ready` 和仅含 `postgres`、稳定安全代码的 dependency 结果。每个服务在现有 Prometheus 端点公开自己拥有的 PostgreSQL readiness 探测总数、失败总数与耗时直方图，不使用 URL、用户名、数据库、异常、SQL、密码或其他无界标签；成功、失败和恢复测试必须验证计数与观测值。SF02 不为 Gateway/Admin/Redis readiness 提前接入，也不增加业务路由；后续持久化路由必须把 ready 状态作为可处理前置条件。

**Rationale**: 现有两个服务已锁定 SQLAlchemy asyncio 与 asyncpg，异步短时探测符合 Python 技术规范。200 形状不变、增加 503 响应可作为 health contract v1 的向后兼容 minor 演进；成功消费者不需解析新字段。

**Alternatives considered**:

- 启动失败导致进程退出：破坏 liveness/readiness 分离，数据库恢复后不能自愈。
- 每个请求创建 engine：资源浪费且难以正确关闭。
- 共享服务内部模块：跨服务实现耦合。
- 把 Redis/Admin/Gateway 一并接入：超出澄清范围。

## Decision 14: Root Make 与工作流事件升级到 v2

**Decision**: 在 `shared/contracts/repository-workflow/v2/` 新建 Make 与 workflow event `2.0.0` 契约。event v2 使用标准事件信封，顶层强制唯一 UUID `event_id`、`event_type=workflow.step`、`schema_version=2.0.0`、UTC RFC 3339 `timestamp`、`producer=repository-workflow`、生命周期运行级 `correlation_id` 与严格 `payload`；payload 承载 action/component/phase/status/code/duration/message，并新增可选 `dependency`（`postgres|redis|grafana`）、`WAITING` 状态与 SF02 稳定诊断码。机器 schema 要求依赖阶段及依赖专属错误携带 `payload.dependency`。v1 Make/event 文件保持不可变。先合入 v2 契约/迁移通知/失败测试且保留 `SF02_NOT_READY`，随后同步全部仓库消费者并完成受保护实现候选；只有 Linux x86_64 与 macOS arm64 的生命周期、安全、持久化、恢复和性能验收均通过后，才原子激活 v2 `dev/dev-down` 与默认 v2 JSONL。v1 资料至少保留到激活后的下一个 tagged release，期间不允许新增 v1 consumer。

**Rationale**: v1 `schema_version=1.0.0` 且 `additionalProperties=false`，严格 consumer 会拒绝标准信封、新字段与枚举；同时 `dev` 从永不成功变成有副作用成功本身也被 SF01 定义为 breaking。把它叫 minor 会违反宪章的版本、事件最小字段与弃用窗口要求。Compose JSON/health 仍只作为适配器输入，不直接成为公共事件。

**Alternatives considered**:

- 把依赖塞入 `phase`/`message`：不可稳定解析，违背明确字段要求。
- 透传 Docker events：缺少工作流动作、pull/validation 和安全诊断语义。
- 创建完全独立事件格式：让根工作流出现两套输出契约。

## Decision 15: 测试分层且不触及开发者资源

**Decision**: 先写纯单元/契约测试，再写真实依赖集成：

1. 纯函数测试覆盖 URL、Unicode/symlink identity、事件、状态机、脱敏、平台/remote context、端口与锁异常。
2. 伪 Docker CLI subprocess 测试覆盖调用顺序、pull 与 60 秒计时分离、重复/冲突操作、部分失败及不泄密。
3. 真实 Compose 集成使用临时工作区 project id、动态 loopback 高端口、合成秘密和测试专属卷，覆盖冷启、10 轮启停、数据保留、Redis 空状态、异常重启、认证失败、端口冲突和跨项目隔离；测试可清理自己带测试标签的 fixture 资源，但没有公开清理命令。
4. API/Billing 用注入 fake probe 覆盖 200/503/恢复/超时，再以固定 PostgreSQL 镜像做查询集成。
5. 增加 dirty tracked/untracked worktree 前后快照与终端 `NO_COLOR`、纯文本、非交互、屏幕阅读器语义回归，确保新生命周期不削弱 SF01 安全与可访问性。
6. 由同一个确定性性能 harness 在 Linux x86_64 CI 与代表性 macOS arm64 主机执行预声明批次，分别统计 60 秒与 15 秒指标并比较标准事件信封；仓库工作流 owner 负责平台与十人文档验收调度，证据只写入已声明的脱敏模板。

**Rationale**: 真实兼容依赖证明认证和恢复，纯测试保证边界场景确定且快速；测试 project 与开发 project 隔离，避免 `make test` 停止或污染开发者环境。

**Alternatives considered**:

- 全部 mock：不能证明 Compose、镜像、信号、网络和数据卷行为。
- 集成测试直接使用当前工作区 project id：可能停止开发者环境或破坏数据。
- 用生产/共享数据库：违反隔离和秘密边界。

## Source hierarchy and conflicts resolved

优先级为工程宪章 → SF01 已落地契约 → 当前 SF02 active spec → V0.1 子 Spec → 通用技术文档/长期 PRD。早期技术示例中的 floating images、`container_name`、`0.0.0.0` 发布、默认密码、`docker-compose` v1、同时启动 Kafka/Prometheus/业务服务和 `down -v` 均不构成 SF02 允许实现。Kafka/Redpanda、Prometheus、Loki、MinIO、前端和业务服务自动启动继续在范围外。
