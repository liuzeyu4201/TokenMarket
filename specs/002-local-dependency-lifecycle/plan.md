# 实施计划：本地依赖环境生命周期

**Branch**: `002-local-dependency-lifecycle` | **Date**: 2026-07-15 | **Spec**: [spec.md](./spec.md)

**输入**: 功能规格来自 `/specs/002-local-dependency-lifecycle/spec.md`

> 以下内容保留当时的实施计划语境。

## 摘要

用真实、有界且非破坏性的本地生命周期，替换 SF01 的失败关闭（fail-closed）`SF02_NOT_READY` 过渡态，公共入口仍保持不变的 `make dev` 与 `make dev-down`。因成功与副作用语义发生变化，须先发布 Root Make Workflow/event v2，并在激活前迁移仓库内全部消费者。维护中的 Python 工作流工具将校验被忽略的本地配置，推导经碰撞检查的路径哈希 Compose 项目身份，用安全的 POSIX 咨询锁（advisory lock）串行化操作，仅拉取已评审的多平台镜像 digest，在仅回环的项目网络上对 PostgreSQL 15/Redis 7/Grafana 做状态协调（reconcile），在单一 60 秒截止时间内执行认证就绪检查，并在普通 down 时保留 PostgreSQL/Redis 命名卷。

实现采用契约优先与测试优先。引入版本化的本地依赖清单；创建符合宪章的 workflow event v2 标准信封，其 payload 承载依赖/`WAITING`/稳定 SF02 诊断；并增加向后兼容的健康契约次要更新：API Service 与 Billing Service 保留独立 liveness，但在有界 PostgreSQL `SELECT 1` 探针失败时返回 503 就绪检查，并暴露安全的 Prometheus 探针总数、失败数与耗时。不启动任何业务服务，不运行迁移/schema/seed，不新增破坏性清理动作，Gateway/Admin 就绪检查保持不变。

## 技术上下文

**语言/版本**: 根工作流/生命周期与 FastAPI 就绪检查使用 Python 3.11.15；兼容 GNU Make 3.81 的入口适配器；Docker Compose YAML；JSON/JSON Schema 2020-12；OpenAPI 3.1；Markdown 运行手册

**主要依赖**: 既有独立 uv 锁定的 `tools/workflow` 包，使用 Python 标准库（`urllib.parse`、`hashlib`、`unicodedata`、`socket`、`fcntl`、`subprocess`），外加已评审的 asyncpg 0.30.x 以支持 PostgreSQL 主机查询；Docker Engine/CLI 29.5.3 与 Docker Compose 5.1.4；PostgreSQL `15.18-bookworm`、Redis `7.2.14-bookworm`、Grafana OSS `13.0.3`，各自由已评审的 index 与 child digest 固定；API/Billing 中既有 FastAPI 0.115.x、SQLAlchemy asyncio 2.0.x 与 asyncpg 0.30.x 锁

**存储**: 项目作用域的 PostgreSQL 命名卷为持久化本地事实源；项目作用域的 Redis 命名卷保留但语义上可重建；Grafana `/var/lib/grafana` 为显式 tmpfs，无匿名/命名卷；密钥从专用 Compose 子进程环境进入由 UID/GID 拥有的 0400 容器密钥文件，且永不成为主机文件；无新业务表、本地元数据数据库或生产数据

**测试**: `tests/workflow/` 下的 pytest/pytest-asyncio 单元与子进程契约测试；JSON Schema/OpenAPI/Compose 结构测试；假 Compose 适配器测试；带合成凭据/动态回环端口的真实隔离 Docker Compose 集成；API/Billing FastAPI 探针注入与真实 PostgreSQL 查询测试；十周期持久化/幂等/并发/恢复套件；Linux x86_64 CI 外加独立的代表性 macOS arm64 性能验收证据

**目标平台**: 带本地 Docker Desktop Linux 容器的 macOS arm64，以及带本地 Docker Engine 的 Linux x86_64；同一 OCI index 的原生 `linux/arm64`/`linux/amd64` 镜像变体；远程 context/端点及其他主机/架构组合不受支持

**项目类型**: 多语言 monorepo 功能，覆盖开发者生命周期 CLI、声明式本地基础设施、版本化共享开发者/健康契约、两个独立拥有的 Python 服务就绪检查适配器、测试与运行手册文档

**性能目标**: 镜像获取单独计量；全部镜像可用后，各受支持主机类上至少 95% 的正常冷启动就绪检查在 60 秒内完成；十次健康重复启动各自在 15 秒内完成，且无 registry 访问或资源计数增长；API/Billing 就绪检查在总计两秒探针超时内完成；冲突/前置检查失败发生在资源变更之前

**约束**: 根 Makefile 为唯一公共工作流；依赖集恰好为 PostgreSQL/Redis/Grafana；禁止系统工具安装/升级、`sudo`、远程 daemon、业务服务启动、Kafka/Prometheus/Loki/MinIO、迁移、seed、生产/测试访问、仅 tag/latest 镜像、通配/局域网绑定、固定容器名、全局/匿名卷、argv/服务环境/输出中的密钥、主机密钥文件、隐式凭据轮换、就绪检查失败时自动回滚/down、卷删除/prune 或破坏性清理目标；含空格/非 ASCII/symlink 的路径与脏工作区仍须安全

**规模/范围**: 每个规范工作区一套项目资源，恰好三个依赖实例、一个项目网络、两个命名卷、一个咨询锁、三个容器密钥文件、一个 Grafana tmpfs、两个感知 PostgreSQL 的服务就绪检查适配器、两类受支持主机/架构，且无 HA/集群容量承诺

**受影响组件**: 根 `Makefile`/`.env.example`；`tools/workflow/` 包发现与 `tests/workflow/`；`infra/docker/` 与 infra 测试；`ops/workflow/` 及本地环境运行手册；新建 `shared/contracts/repository-workflow/v2/`（v1 保持不可变），以及 local-environment 契约副本；`services/api-service/` 与 `services/billing-service/`；仓库/infra 文档与 ADR 002

**契约**: Root Make Workflow v2 版本化破坏性的 dev/dev-down 成功/副作用语义与迁移窗口；workflow event v2 使用必填 `event_id`、`event_type`、`schema_version`、UTC `timestamp`、`producer`、`correlation_id` 与 `payload`，payload 承载依赖、`WAITING` 与稳定 SF02 诊断且不修改 v1；本地依赖清单/生命周期 v1 拥有 index 加 child digest、URL 语法、碰撞安全身份、锁、资源、探针、持久化与恢复；service health v1.1 仅为 API/Billing 增加 503 依赖就绪检查响应，端点特定 200/liveness 形状保持精确

**数据与迁移**: 无 Alembic 修订或 schema 变更。API/Billing 仍为迁移所有者，但生命周期永不调用迁移。锁加精确 Compose 项目身份提供操作幂等/状态协调，而非数据存储事务。普通 down 保留全部命名卷；既有卷上的 PostgreSQL 角色/密码不匹配会使就绪检查失败，并要求显式手工恢复，永不隐式变更角色。仅测试用的可丢弃卷可由其隔离夹具 teardown 删除。

**安全与隐私**: 纯 action/mode 校验先于身份与一切资源访问；只读清单/运行时/配置/端口前置检查先于锁文件创建，随后在锁内、变更前再次校验端点/所有权/端口；仅 `.env.local` 提供生命周期值，且仅接受 `127.0.0.1` URL；解码后的密钥须符合可注入安全的 `tm_local_` 语法，且仅通过专用 Compose 子映射传入由已验证非 root 镜像 UID 拥有的 0400 environment-source 密钥挂载；主机/服务环境、argv、事件、日志或夹具均不得含值；已提交 Compose 字节经校验后经 stdin 管道传入，项目目录仅由项目 ID 推导，使规范 Compose 标签无法泄露工作区路径；确定性每用户运行时路径拒绝 symlink/所有者/模式漂移；未知端口不接收凭据；Compose/inspect/health 输出被捕获、最小解析并脱敏；远程 Docker 端点失败关闭；index/child digest、许可证与扫描覆盖双平台

**可观测性与可靠性**: 一个信封级 `correlation_id` 关联可访问的纯文本与 JSONL v2 记录，每条记录具有唯一事件 ID、UTC 时间戳、producer 与稳定事件类型；每个机器定义的依赖 payload 携带依赖、耗时与安全码；拉取与就绪检查时钟分离，而状态协调与并发探针共享一个不可延长的 60 秒截止时间；最终快照使用 Compose JSON 加即时认证探针，永不使用陈旧健康；同项目操作非阻塞串行，每一个失败争用的命令立即返回 `OPERATION_IN_PROGRESS`；失败时保留可检查状态与命名卷；down 协调已停止容器/网络且可在无密钥时重复；这些本地 CLI 失败是用户可见的严重性/动作状态而非 pager 告警，由仓库/infra/服务团队拥有并链接到运行手册；API/Billing liveness 保持独立，就绪检查在 PostgreSQL 恢复后自愈，安全的探针总数/失败/耗时经既有 Prometheus 端点暴露

**部署与回滚**: 无生产部署或镜像发布。ADR 002 在实现前作为设计决策被接受，而实现验证保持 Pending。分阶段上线：在 v1 行为仍保留时发布 v2 契约/迁移通知/失败测试，迁移全部消费者，加入已验证 digest/Compose/适配器/就绪检查以及 Linux x86_64 与 macOS arm64 生命周期/安全/性能验收证据，然后原子激活 v2 目标、事件信封、帮助与恢复文档并记录实现验证。回滚为经评审的一并还原 manifest/Compose/适配器/v2 激活/服务探针，恢复 v1 事件加 `SF02_NOT_READY` 失败关闭行为并保留版本历史；永不删除既有项目卷。镜像回滚须同时变更 tag/index/child digest 与扫描。

## 宪章检查

*GATE: 在 Phase 0 研究前通过，并在 Phase 1 设计后复核。*

### 研究前门禁

| 门禁 | 状态 | 证据 / 决策 |
|------|--------|---------------------|
| 架构与所有权 | PASS | 复用已批准的根工作流与 infra 边界；Compose 是适配器而非服务；API/Billing 拥有独立探针；无跨服务导入/存储；重要编排决策记录在 ADR 002 |
| 契约与兼容性 | PASS | Root Make/event v2 显式版本化破坏性成功/副作用与严格事件变更；event v2 使用宪章要求的标准信封；v1 Make/event 文件在已文档化的消费者迁移/弃用窗口内保持不可变；生命周期/清单/健康接口先于实现 |
| 安全与隐私 | PASS | 仅本地 mode/端点、回环字面量、严格合成语法、为已验证非 root UID 提供 Compose environment-source 0400 密钥文件、安全锁路径、脱敏与官方 digest/扫描/许可证评审，在资源创建前规划 |
| 数据正确性 | PASS | PostgreSQL/Redis/Grafana 持久化等级、项目所有权、锁/状态协调、卷保留与无迁移/无删除规则明确；不引入业务数据模型 |
| 测试 | PASS | 单元、契约、假子进程、真实兼容依赖、认证/端口/并发/中断/持久化、脏工作区、终端可访问性与共享测试框架（harness）平台/性能测试先于激活 |
| 运维 | PASS | liveness/就绪检查分离、一个不可延长的就绪检查截止时间、有界每服务/外层 stop 限制、逐依赖脱敏信封事件、API/Billing 就绪检查指标、本地无 pager 严重性理由、恢复/运行手册所有权与平台 SLO 验收证据已定义 |
| 交付 | PASS | 独立工作流锁接收已评审的 asyncpg 增量而服务锁不变；Docker/Compose/镜像精确；CI/本地根门禁、依赖影响、上线/回退与可追踪性已规划 |

无需例外或临时豁免。ADR 002 在生命周期实现前由 Proposed 变为 Accepted 作为设计批准；实现验证在双平台验收证据通过前保持 Pending。

### 设计后门禁

| 门禁 | 状态 | Phase 1 证据 |
|------|--------|------------------|
| 架构与所有权 | PASS | [data-model.md](./data-model.md) 分离 Git 事实、开发者密钥、项目资源、操作与每服务就绪检查；[ADR 002](../../docs/decisions/002-local-compose-lifecycle.md) 记录替换边界 |
| 契约与兼容性 | PASS | [contracts/](./contracts/) 在运行时消费者之前定义 Root Make/event v2 标准信封迁移、生命周期调用/配置/身份/状态/恢复、清单 schema 与 service health v1.1；严格 v1 读取器在激活前迁移 |
| 安全与隐私 | PASS | 生命周期契约固定合成 URL 密钥语法、Compose 拥有的密钥文件、安全锁存储、无凭据端口检查、远程 context 拒绝、index/child 校验与安全诊断；quickstart 禁止密钥型验收证据 |
| 数据正确性 | PASS | 数据模型定义事实源、锁/状态协调不变量、持久/可重建/临时等级、无迁移与无删除；quickstart 测试标记保留 |
| 测试 | PASS | [quickstart.md](./quickstart.md) 与验证矩阵覆盖正负、集成、恢复、并发、脏工作区、终端可访问性、共享测试框架（harness）性能与双主机平台 |
| 运维 | PASS | 逐依赖健康结果、即时状态规则、共享就绪检查截止时间、60/30 服务优雅期加 75 秒 stop 边界、workflow v2 标准关联信封、API/Billing 503、就绪检查指标与失败恢复已契约化 |
| 交付 | PASS | 精确运行时/镜像版本、digest 物化门禁、双平台验收证据、分阶段上线与失败关闭回退已规定 |

设计后结果：**纠正审计后 PASS — 无未解决澄清、占位设计决策或无正当理由的宪章违反。** 初稿中未版本化的 Make/event 变更、顺序超时溢出与主机文件/非 root 不匹配，已由 v2 迁移、单一截止时间与 Compose environment-source 密钥所有权关闭。实际 OCI index/child digest 值仍是实现侧供应链产物：schema 拒绝缺失身份，且在注册表解析与双平台验证提交前，实现无法通过第一道门禁。

## 项目结构

### 文档（本功能）

```text
specs/002-local-dependency-lifecycle/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── local-environment-lifecycle.md
│   ├── local-dependency-manifest.schema.json
│   ├── make-workflow-v2.md
│   ├── workflow-event-v2.0.schema.json
│   └── service-health-v1.1.openapi.yaml
├── evidence/
│   ├── README.md                          # 已脱敏验收证据索引与所有权
│   ├── quality-gates.md
│   ├── linux-amd64.md
│   ├── macos-arm64.md
│   └── developer-usability.md
└── tasks.md                              # 稍后由 /speckit-tasks 创建
```

### 源码（仓库根）

```text
Makefile                                  # 稳定的 dev/dev-down 委托与仅更新的 help
.env.example                              # SF02 字段、注释与不可用占位符
CLAUDE.md                                 # 活动功能上下文
docs/decisions/
└── 002-local-compose-lifecycle.md         # 实现合入前已 Accepted
tools/workflow/
├── pyproject.toml                        # 发现 workflow 与 workflow.local_env 包
├── cli.py                                # 仅替换 SF02 过渡分发
├── events.py                             # Event v2 发射器/错误码/脱敏
├── security.py                           # 复用/扩展严格安全配置原语
└── local_env/
    ├── __init__.py
    ├── models.py                         # 类型化内部实体/状态
    ├── config.py                         # .env.local 与 URL 校验/推导
    ├── identity.py                       # 规范路径哈希与 fcntl 锁
    ├── compose.py                        # 已验证 stdin/安全项目目录 Compose JSON 适配器
    ├── probes.py                         # PostgreSQL/Redis/Grafana 安全探针
    └── lifecycle.py                      # 有序 dev/dev-down 编排
tests/workflow/
├── test_sf02_transition.py               # 变为过渡替换兼容性测试
├── test_local_env_config.py
├── test_local_env_identity.py
├── test_local_env_events.py
├── test_local_env_compose.py
├── test_local_env_lifecycle.py
├── test_local_env_concurrency.py
├── test_local_env_security.py
├── test_local_env_dirty_worktree.py
├── test_local_env_performance.py
├── test_accessibility_performance.py      # 扩展 SF01 终端可访问性覆盖
└── test_local_env_integration.py          # 仅隔离真实 Compose 项目
infra/
├── docker/
│   ├── compose.local.yml                 # 恰好 postgres/redis/grafana
│   └── README.md
└── tests/
    └── test_local_compose.py             # 结构、digest、绑定、卷、密钥测试
ops/
├── workflow/
│   ├── toolchains.json                   # Compose + 当前镜像完整性来源
│   └── local-dependencies.json           # 运行时清单；无密钥/占位 digest
└── runbooks/
    └── local-environment.md               # 安全检查/恢复/工作区移动指南
shared/contracts/
├── repository-workflow/v1/
│   ├── make-workflow.md                  # 不可变的 SF01 失败关闭历史
│   ├── workflow-event.schema.json        # 不可变 1.0.0 历史
│   └── service-health.openapi.yaml       # 仅健康的次要 1.1.0
├── repository-workflow/v2/
│   ├── make-workflow.md                  # 破坏性 SF02 激活/迁移
│   └── workflow-event.schema.json        # 2.0.0
└── local-environment/v1/
    ├── lifecycle.md
    └── local-dependency-manifest.schema.json
services/
├── api-service/
│   ├── app/
│   │   ├── main.py                       # 生命周期拥有的 engine/探针
│   │   ├── health.py                     # 200/503 契约适配器
│   │   ├── database.py                   # 自有 async SELECT 1 探针
│   │   └── observability.py              # 安全就绪检查计数/直方图
│   └── tests/
│       ├── test_health.py
│       ├── test_database_readiness.py
│       └── test_readiness_metrics.py
└── billing-service/
    ├── app/{main.py,health.py,database.py,observability.py}
    └── tests/{test_health.py,test_database_readiness.py,test_readiness_metrics.py}
```

**结构决策**: 将编排放在维护中的仓库工作流包中，将声明式资源放在 `infra/`；更新 setuptools 发现使 `workflow.local_env` 包含在已安装/锁定执行中；将已评审环境事实存于 `ops/workflow/`，可复用接口存于版本化 `shared/contracts/`。API/Billing 仅各自复制小型自有探针适配器，使任一服务都不导入对方实现。不引入新服务、数据存储、共享业务包、公共脚本、Compose override 或破坏性命令。

## 实施策略

### Phase A — 契约物化、ADR 接受与失败测试

1. 在生命周期实现前将 ADR 002 接受为已批准设计，将实现验证标为 Pending，并从 infra/运行手册/可追踪文档链接之。
2. 将 Root Make/event v2 标准信封、生命周期/清单与健康契约复制到版本化运行时位置，同时保持 v1 Make/event 产物不可变；发布激活/弃用通知，并在本阶段保持可执行的 `SF02_NOT_READY` 行为。
3. 枚举每个仓库拥有的事件消费者，并添加在缺失 v2 支持时先失败的迁移测试；另行添加未来生命周期测试，同时保留目标名称与纯 mode-先于锁的安全顺序。
4. 为仅 tag/latest/缺失 index 或 child 身份、额外服务、通配端口、`container_name`、全局/匿名/已删除卷、嵌入/服务环境密钥、缺失 healthcheck 与缺失 Grafana tmpfs 添加清单/Compose 结构负向夹具。
5. 将三个官方精确 tag 解析为真实 OCI index/child digest，验证双原生架构，捕获许可证/扫描验收证据，并提交 `ops/workflow/local-dependencies.json`；将既有 PostgreSQL 15.12 占位完整性引用作为一次已评审依赖变更更新。

**退出验收证据**: 契约校验通过；ADR 已接受；测试仅因缺失运行时行为而失败；任何占位 digest 或不安全 Compose 形态均无法通过 `contracts-check`/infra 测试。

### Phase B — 纯配置、身份、事件与锁核心

1. 在实现前添加类型化模型/状态转换与测试。
2. 先实现纯 Make-mode 来源校验，再实现 `.env.local` 解析、严格 `tm_local_` 解码密钥语法、URL/端口推导与仅字段名错误。
3. 实现规范物理路径 + NFC + UTF-8 SHA-256 短 ID 与全指纹，覆盖空格/中文/symlink/大小写/不同 worktree/移动/碰撞夹具；证明输出或任何自定义/Compose 规范资源元数据中无路径。
4. 实现确定性安全每用户/项目运行时基目录、空 Compose 项目目录与非阻塞 `fcntl` 边界；拒绝 symlink/类型/所有者/模式漂移，并证明争用与异常持有者退出。
5. 将 `workflow.local_env` 加入 setuptools 包发现，并将 asyncpg 0.30.x 加入独立工作流锁而不改服务锁。实现 event v2 标准信封发射器/schema/消费者支持（唯一事件 ID、UTC 时间戳、producer/type/correlation 字段、依赖阶段 payload 要求与更广脱敏），并在激活前保持 v1 Make/event 产物与测试不可变。

**退出验收证据**: 纯单元/契约套件在无 Docker 时通过；被拒绝的前置检查案例不创建任何 Docker/socket/配置或协调产物；仅在前置检查通过且锁获取开始后，已验证安全运行时目录、Compose 项目目录与锁文件可以存在；v1 回归与 v2 消费者迁移套件均通过。

### Phase C — Compose 定义与安全运行时适配器

1. 添加恰好三个 index-digest 镜像、规范服务名、项目作用域默认网络、长语法 `127.0.0.1` 端口、PostgreSQL/Redis 命名卷、显式 0700 运行时 UID/GID 拥有的 Grafana `/var/lib/grafana` tmpfs、认证 healthcheck、已验证上游非 root UID 与 60/30/30 stop 优雅期的 `compose.local.yml`。
2. 实现顶层 environment-source Compose 密钥与 PostgreSQL/Grafana 密码及单指令 Redis 配置的长语法 0400 UID/GID 目标；使用专用子映射，并证明值永不进入 argv、服务环境、Compose 模型输出、inspect 快照、主机文件或工作区。
3. 实现带固定全局参数、已提交 blob 相等检查、经 `-f -` 的已验证 YAML 字节、安全运行时项目目录、捕获的 JSONL `ps`、最小 inspect 字段、pull/up/down 命令、本地端点/平台/能力校验与未知字段容忍解析的 Compose 适配器。拒绝脏/被替换/symlink 的 Compose 资产，并扫描全部结果规范标签中的原始/规范工作区路径。
4. 实现项目短 ID/全指纹所有权检查、失败关闭的碰撞处理、强制只读旧资源报告、在保留卷的前提下替换精确拥有的但非当前镜像、发布者检查与仅绑定端口的前置检查/竞态映射。
5. 为精确参数顺序、无 `-v`/prune/镜像删除、缺失配置的 down、远程 context 拒绝、畸形 JSON、脱敏与中断子进程添加假 CLI 测试。

**退出验收证据**: Infra/适配器套件在任何真实依赖测试前证明期望模型；无密钥或原始 Docker 错误在序列化后残留。

### Phase D — 生命周期编排与真实依赖验收证据

1. 将 `dev` 阶段实现为只读前置检查 → 获取安全锁 → 再校验端点/所有权/端口 → 子密钥映射 → 仅缺失拉取 → index/child digest 校验 → 一个 60 秒截止时间 → `up --detach --pull never` → 仅用剩余时间做并发当前状态/认证探针 → 聚合；每个可变阶段均在锁下。
2. 实现 PostgreSQL 认证 TCP `SELECT 1`、带 `REDISCLI_AUTH` 的 Redis AUTH/PING，以及 Grafana health/admin 探针，带每次剩余时间边界、无截止后成功与安全结果类别。
3. 实现健康快速路径、已停止/陈旧/部分状态协调、超时状态保留、中断/daemon 丢失重试，以及精确项目的工作区移动报告。
4. 实现无需配置的 `dev-down`、安全仅解析子密钥、无容器/网络时的 `already stopped` 规则、精确项目的 `down --remove-orphans` 且无 CLI 超时覆盖、声明的 60/30/30 服务优雅期、75 秒外层边界、精确回退与停止后/卷校验。
5. 在 v2 消费者迁移门禁通过后，在既有失败关闭激活护栏后，完成 `cli.py` 中激活候选的 dev/dev-down 分发与 event-v2 信封路径；本阶段不移除公共运行时 `SF02_NOT_READY` 行为。
6. 对冷/已拉取镜像阶段、十次重复启动、十次 start/down/restart 循环、PostgreSQL 标记保留、空 Redis、零 Grafana 匿名卷、错误认证/配置注入、端口冲突/竞态、部分/不健康/已停止状态、截止边缘、强制中断、锁冲突、哈希碰撞与双工作区隔离运行隔离真实 Compose 测试。短生命周期仅测试容器挂到精确项目网络，经 stdin 接收合成探针材料，并对三个规范服务 URL 执行 PostgreSQL 查询、Redis AUTH/PING 与 Grafana health/admin HTTP 调用；仅 DNS 解析不够。

**退出验收证据**: 除服务就绪检查与跨主机性能外的全部生命周期成功标准，在 Linux x86_64 上通过受保护的候选适配器；夹具清理不得指向开发者项目 ID，且公共 Make 入口保持失败关闭。

### Phase E — API/Billing 依赖感知就绪检查

1. 在改变服务行为前将共享健康 OpenAPI 更新到 v1.1。
2. 在每个服务中，为 liveness 独立性、200 ready、503 invalid-config/connection/auth/query/timeout、安全 payload/日志、无重启恢复、两秒边界，以及无密钥的 Prometheus 探针总数/失败/耗时指标编写失败测试。
3. 使用既有锁定依赖与 `pool_pre_ping` 添加生命周期拥有的 SQLAlchemy async engine/探针；在内部将生命周期 `postgresql://` URL 安全映射到 asyncpg，并在关闭时 dispose。
4. 通过 application state/测试依赖注入探针；成功响应字段保持不变，仅在 503 时发出契约化的单一 PostgreSQL 结果，并为成功、失败与恢复更新服务自有的低基数就绪检查计数器与耗时直方图。
5. 独立运行 API 与 Billing 的真实 PostgreSQL 探针集成。确认 Gateway/Admin 源码/测试/契约未获得依赖探针，且未添加业务路由。

**退出验收证据**: 健康契约测试与真实查询/恢复测试通过；PostgreSQL 中断时 liveness 保持 200，且无需服务重启即可将就绪检查恢复到 200。

### Phase F — 文档、平台矩阵与上线门禁

1. 用配置、服务名、项目/移动语义、安全地址、数据/停止效果、诊断、无密钥安全检查与恢复更新 `.env.example`、根/infra/服务文档与 `ops/runbooks/local-environment.md`。
2. 添加并运行显式终端可访问性与脏工作区保留测试，然后运行完整 `make lint`、`make test`、`contracts-check`、安全/密钥检查与结构链接校验；验证 `NO_COLOR`/纯文本/屏幕阅读器语义、脏已跟踪/未跟踪文件不变、无跟踪/主机密钥文件、无缺失 digest 身份、包发现遗漏或锁漂移。
3. 实现双平台不变使用的确定性共享测试框架（harness）。在 Linux x86_64 上执行其预先声明的 20 次冷启动批：镜像已校验、每次试验无项目容器/网络且全新隔离测试自有卷；统计每一次合法试验，并要求至少 19/20 在 60 秒内达到三个就绪状态。亦在 CI 中记录原生镜像变体、十次重复计时、信号、十周期持久化与全部失败套件。
4. 在代表性 macOS arm64 上重复同一 20 次/19 通过算法，外加原生变体、路径/NFC、Desktop 回环、Compose 密钥所有权、健康、stop 与十次重复 ≤15 秒验收证据；与 Linux 比较 event v2 行为。前置/工具链失败会使整批声明作废并重跑，而不是排除偏慢试验。
5. 仓库工作流负责人按已提交的验收证据模板与参与者标准，安排并执行 [quickstart.md](./quickstart.md)，对象为 10 名此前未使用 SF02 的代表性开发者。从前置已就绪的 checkout 起，仅允许根帮助与本地环境文档；要求至少 9/10 在 10 分钟内独立完成配置准备、启动、确认三态并定位一条注入故障的恢复说明。仅附带已脱敏汇总验收证据。
6. 仅在双平台报告、可访问性/安全/脏工作区门禁、消费者迁移、文档与生命周期验收证据均通过后，原子移除 `SF02_NOT_READY`，激活 dev/dev-down 与 event v2 及匹配的帮助/恢复文本，并在不改变其已 Accepted 设计状态的前提下，标记 ADR 实现验证与功能完成。

**退出验收证据**: 双平台满足相同功能/输出契约及其分别计算的性能目标；公共 v2 激活是原子的；ADR/PR 将设计接受与实现验证、依赖、契约、schema/安全影响、上线与保留卷的回滚分开记录。

## 验证矩阵

| 需求区域 | 计划自动化验收证据 | 手工/评审验收证据 |
|------------------|----------------------------|------------------------|
| US1 / FR-001–015 | 目标兼容；严格前置检查；清单/digest；拉取/就绪检查时钟分离；端口冲突；真实探针；冷/重复/部分/重试测试 | 安全输出、主机地址、每平台 ≤60s/≤15s 验收证据 |
| US2 / FR-016–023 | 身份/路径/worktree/移动/碰撞夹具；全部自定义与 Compose 规范标签中无原始/规范路径；精确指纹所有权；含已停止资源的无配置 down；十次持久化循环；零匿名/已删除卷；安全锁/并发/异常退出测试 | 旧资源恢复措辞与 PostgreSQL 标记保留评审 |
| US3 / FR-007–012, FR-024–026 | URL/推导地址与密钥语法测试；仅测试用项目网络 PostgreSQL 查询、Redis AUTH/PING 与 Grafana 认证 HTTP 探针；event v2 标准信封 schema/迁移；API/Billing 精确 200/503/恢复形状加安全就绪检查指标；Gateway/Admin 无变更断言 | 运行手册易用性与 10 人新开发者练习（≥9/10 在十分钟内） |
| FR-027–029 | 子进程 denylist/快照；运行时锁文件不可变与已评审实现锁变更检查；脏已跟踪/未跟踪工作区前后测试；相同 Compose 定义与原生镜像平台检查 | macOS arm64 + Linux x86_64 矩阵对比 |
| ER-001–003 | 契约版本/漂移测试；密钥/远程/通配/argv 扫描；卷/schema/迁移负向断言 | Digest/许可证/安全评审与回滚身份 |
| ER-004–007 | 共享确定性测试框架（harness）；逐阶段单调计时；幂等/并发/中断；已脱敏标准信封 JSONL；服务就绪检查指标；纯文本/NO_COLOR/非交互输出；优雅 stop 测试 | 分主机性能报告与屏幕阅读器/纯文本评审 |
| SC-001–009 | 每平台 20 次冷启动且 ≥19/20 ≤60s、十次重复/循环、真实隔离连接探针、全部命名负向夹具、双工作区隔离与 100 次并发冲突 | 十名代表性新开发者 ≥9/10 在十分钟内，外加验收证据检查清单 |

## 测试优先顺序

对每个切片，行为测试/契约变更先于其实现落地：

1. 运行时契约副本、清单与 Compose 结构夹具。
2. 不可变 Make/event v1 回归，外加 event v2 标准信封迁移、身份/时间戳/producer/correlation、payload 依赖与诊断 schema 测试。
3. 配置/URL/密钥脱敏纯测试。
4. 身份、所有权、锁与工作区移动纯测试。
5. 假 Compose 命令/顺序/JSON/错误/中断测试。
6. 真实镜像、网络、健康、持久化、stop 与重试测试。
7. 并发与跨工作区隔离测试。
8. API/Billing 假探针健康契约测试。
9. API/Billing 真实 PostgreSQL 查询/恢复与就绪检查指标测试。
10. 脏工作区与终端可访问性回归。
11. 共享测试框架 Linux/macOS 性能与 quickstart 验收。

变更的 Python 工作流/服务包要求至少 80% 行覆盖率。负向断言直接覆盖配置信任、密钥泄露、所有权、并发、幂等、超时、数据保留、禁止的迁移/清理与回滚安全。

## 上线与回滚

### 上线

1. 将 ADR 002 接受为设计决策，然后合入 Root Make/event v2 契约、迁移通知、清单 schema 与失败测试，同时运行时行为仍保持 v1 `SF02_NOT_READY`；保持 ADR 实现验证 Pending。
2. 解析/扫描/提交真实三镜像多平台 digest；在 Compose 使用前拒绝任何不受支持架构或占位。
3. 在测试后落地纯工作流核心与 Compose 适配器，同时 dev/dev-down 仍失败关闭。
4. 迁移全部已枚举仓库消费者并完成受保护的激活候选，同时公共 dev/dev-down 仍返回 `SF02_NOT_READY`。
5. 在共享健康 v1.1 物化后添加 API/Billing 就绪检查与安全探针指标。
6. 公共激活前要求可访问性、脏工作区、安全、Linux x86_64 CI 与代表性 macOS arm64 验收证据；记录共享测试框架（harness）与已脱敏验收证据。
7. 原子地将 dev/dev-down 从 `SF02_NOT_READY` 切换，使 event-v2 信封成为默认，发布匹配的帮助/恢复文本，公告激活/弃用窗口、Grafana tmpfs 状态、PostgreSQL 凭据漂移恢复与工作区移动/碰撞语义，然后标记 ADR 实现验证与功能完成。v1 产物保留至下一 tagged release。

### 回滚

- 经评审 PR 回退；永不 reset/force-push 或删除本地卷。
- 将 Compose 资产、依赖清单、工作流适配器、事件/健康契约、API/Billing 探针、测试与文档作为一套兼容集合一并回退。
- 若无法迅速恢复安全生命周期，恢复 SF01 的 `SF02_NOT_READY` 预配置/预 Docker 失败，而不是报告虚假成功。
- 保持项目作用域 PostgreSQL/Redis 卷不动以待前向修复；回滚无破坏性清理步骤。
- 通过同时提交先前 tag + index digest + 两个 child digest + 扫描/许可证验收证据回滚镜像。
- 若真实密钥暴露，先吊销/轮换并审计；生命周期回滚不重写历史，也不静默变更 PostgreSQL 角色。

## 复杂度追踪

无计划中的宪章违反或临时例外。`tools/workflow/local_env/` 包由本功能独立的配置、身份/锁、Docker 适配器、探针与编排边界所正当化；它仍是既有工作流组件下的内部适配器，而非新的运行时服务。两个小型服务自有的数据库探针有意避免跨服务实现依赖。
