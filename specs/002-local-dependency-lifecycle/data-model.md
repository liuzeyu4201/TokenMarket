# 数据模型：本地依赖环境生命周期

**Feature**: `002-local-dependency-lifecycle`
**Date**: 2026-07-15
**持久化模型**: Git 跟踪的依赖定义，外加项目作用域 Docker 资源与临时健康/操作验收证据；无 TokenMarket 业务 schema

## 概述

```text
LocalDependencyManifest 1 ── 3 LocalDependencyDefinition
            │                         │
            │                         ├── 1 DerivedConnection
            │                         └── 0..1 NamedVolumeDefinition
            │
LocalEnvironmentConfiguration 1 ── 3 DerivedConnection
            │
            └── 1 ProjectResourceSet ── 3 DependencyInstance
                         │                       │
                         ├── 1 LifecycleLock    └── * DependencyHealthResult
                         ├── 0..1 LifecycleOperation ── * WorkflowEvent
                         └── * ComposeSecretMaterial

api-service     1 ── * ServiceReadinessResult(postgres) ── 1 ServiceReadinessMetrics
billing-service 1 ── * ServiceReadinessResult(postgres) ── 1 ServiceReadinessMetrics
```

定义由仓库拥有并受版本控制。真实本地配置与内存中的密钥材料由开发者拥有且永不跟踪。Docker 资源是本地可变状态。健康/就绪检查结果与工作流事件是短生命周期验收证据，在新操作或 daemon 重启后不得再作为当前事实复用。

## 实体：LocalDependencyManifest

仓库拥有的 SF02 依赖集与生命周期常量的事实源。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `schema_version` | semantic version | 首个 SF02 清单为 `1.0.0` |
| `diagnostic_contract_version` | semantic version | `2.0.0`；Root Make/event v2 激活 |
| `project` | object | `prefix=tokenmarket`；SHA-256 规范 NFC UTF-8 路径；12 字符项目后缀加 64 字符碰撞指纹；经 stdin 的已提交 Compose 字节、安全运行时项目目录与 POSIX 锁机制 |
| `runtime` | object | Docker `29.5.3`、Compose `5.1.4`、本地 Unix 端点、environment-source Compose 密钥文件，以及有序主机 `darwin/arm64`、`linux/amd64` |
| `timeouts` | object | 就绪检查 `60`、健康重复 `15`、完整 stop 操作 `75` 秒 |
| `dependencies` | ordered list | 恰好 `postgres`、`redis`、`grafana`；无可选第四依赖 |

**不变量**：

- 清单校验与 digest/平台验证发生在 Compose 创建或修改资源之前。
- 版本/digest/许可证/平台变更是已评审的依赖契约变更，并更新 ADR/扫描验收证据。
- 任何字段均不得含真实 URL 密码、Grafana 管理员密码、绝对工作区路径、生产地址或用户数据。

**所有者/事实源**: 仓库/infra 维护者；计划运行时路径 `ops/workflow/local-dependencies.json`，由 `contracts/local-dependency-manifest.schema.json` 校验。

## 实体：LocalDependencyDefinition

定义且仅定义一个必需依赖。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `id` | enum | `postgres`、`redis`、`grafana` |
| `repository` | OCI repository | 仅官方/Verified Publisher 允许列表 |
| `version_tag` | exact tag | PostgreSQL `15.18-bookworm`；Redis `7.2.14-bookworm`；Grafana `13.0.3` |
| `index_digest` | OCI SHA-256 | `sha256:` + 64 位小写十六进制；要求真实值，拒绝占位 |
| `platform_digests` | object | 精确的 `linux_amd64` 与 `linux_arm64` child digest |
| `required_platforms` | ordered tuple | 按 schema 顺序恰好 `linux/amd64`、`linux/arm64` |
| `service_name` | enum | 与 `id` 相同；稳定的容器网络 DNS 名 |
| `host_url_field` | enum | 分别为 `DATABASE_URL`、`REDIS_URL`、`GRAFANA_URL` |
| `container_port` | integer | 分别为 5432、6379、3000 |
| `default_host_port` | integer | 相同默认值；实际主机端口仅来自 URL |
| `host_bind_address` | IP literal | 恰好 `127.0.0.1` |
| `liveness_probe` | enum | 容器/进程状态加依赖特定的低风险探针 |
| `readiness_probe` | enum | 认证、无副作用的期望结果 |
| `durability` | enum | `durable-fact`、`preserved-rebuildable`、`ephemeral` |
| `secret_transport` | enum | PostgreSQL 密码文件、Redis 配置文件或 Grafana 密码文件 |
| `volume` | optional object | PostgreSQL/Redis 需要命名卷；Grafana 缺省 |
| `ephemeral_storage` | optional object | Grafana 在 `/var/lib/grafana` 需要 tmpfs，mode 0700，由已验证运行时 UID/GID 拥有；PostgreSQL/Redis 缺省 |
| `stop_grace_period_seconds` | positive integer | PostgreSQL 60；Redis/Grafana 30 |
| `runtime_uid`, `runtime_gid` | positive integer | 从每个固定目标镜像验证，并用作密钥文件所有者 |
| `runtime_uid_policy` | enum | `verified-upstream-non-root-secret-owner`；有效 PID 1 与密钥访问经测试 |

**依赖不变量**：

- `image_ref = repository + ":" + version_tag + "@" + index_digest`；仅 tag、缺失 child-digest 映射与仅 leaf 身份均无效。
- PostgreSQL 最终就绪检查要求对配置库做认证 TCP `SELECT 1`。
- Redis 最终就绪检查要求在同一连接上 AUTH + `PING` → `PONG`。
- Grafana 最终就绪检查要求健康数据库 `ok` 与认证的 server-admin 身份。
- 任何定义不依赖另一依赖。不出现 Kafka、Prometheus、Loki、MinIO、frontend 或业务服务。

## 实体：LocalEnvironmentConfiguration

开发者拥有的真实本地配置，仅从被忽略的 `.env.local` 解析，且仅用于 `make dev`。

| 字段 | 类型 | 分类 | 校验 |
|-------|------|----------------|------------|
| `MODE` | enum | 公共本地元数据 | 恰好 `local`；不能选择有效 mode |
| `DATABASE_URL` | URL | secret | PostgreSQL 语法，用户/密码/库存在，主机 `127.0.0.1`；解码密码匹配本地密钥语法 |
| `REDIS_URL` | URL | secret | Redis 默认用户/密码/db 存在，主机 `127.0.0.1`；解码密码匹配本地密钥语法 |
| `GRAFANA_URL` | URL | internal | HTTP，无 user-info，仅根路径，主机 `127.0.0.1` |
| `GRAFANA_ADMIN_PASSWORD` | string | secret | 匹配 `^tm_local_[A-Za-z0-9_-]{32,96}$` |

**不变量**：

- 三个端口合法且两两不同。
- 查询串、fragment、非回环主机、空/工作默认值、test/prod 标记与看起来像生产的主机均被拒绝。
- 百分号解码仅在语法校验后进行；每个密钥必须匹配 `^tm_local_[A-Za-z0-9_-]{32,96}$`，排除控制/配置语法，且永不放入消息、异常、快照或事件。
- Shell 变量不覆盖生命周期配置。`.env.local` 不能提升命令的有效 mode。
- `make dev-down` 既不需要也不校验本实体。

**保留**: 被忽略的开发者文件；可随时轮换/删除。既有卷的 PostgreSQL 凭据轮换不由 SF02 隐式执行；不匹配会使就绪检查失败，并使用显式恢复流程。

## 实体：DerivedConnection

由已校验主机 URL 创建的不可变内存投影。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `dependency_id` | enum | 一个依赖 |
| `host_scheme` | string | 已校验的依赖 scheme |
| `host_address` | string | 仅 `127.0.0.1` |
| `host_port` | integer | 由 URL 推导 |
| `container_host` | enum | `postgres`、`redis`、`grafana` |
| `container_port` | integer | 由定义推导，永不由用户覆盖 |
| `container_url` | URL | 保留 scheme/user-info/path；将 host/port 替换为服务名/容器端口 |
| `username` | optional string | PostgreSQL/Redis 已校验值 |
| `secret` | optional secret string | 仅在创建专用 Compose 子映射或有界探针环境时短暂持有 |
| `database` | optional string/int | PostgreSQL 库名或 Redis DB 编号 |

**不变量**: 本投影不序列化到日志/事件。仅可展示移除 user-info 后的安全主机地址，例如 `postgresql://127.0.0.1:5432/tokenmarket`。

## 实体：ProjectResourceSet

由一个规范工作区身份拥有的全部本地资源。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `workspace_hash` | 12-char hex | 由工作区根重算；永不接受本地配置输入 |
| `workspace_fingerprint` | 64-char hex | 同一 SHA-256 全量；碰撞/所有权标签，非原始路径 |
| `project_id` | string | `tokenmarket-<workspace_hash>` |
| `labels` | map | 精确仓库、短工作区 ID 与全指纹；自定义标签不含路径，Compose 规范标签可仅含安全运行时目录且永不含工作区路径 |
| `containers` | set | 每个必需服务至多一个 |
| `network` | set | 运行时至多一个项目作用域默认网络 |
| `named_volumes` | set | 仅 PostgreSQL 与 Redis 卷；普通 down 后保留 |
| `runtime_directory` | host path handle | 确定性安全每用户/项目基目录；含 0600 锁与空 0700 Compose 项目目录，无密钥/原始工作区路径，且不输出 |
| `current_operation` | optional reference | 至多一个持锁生命周期操作 |

**不变量**：

- 状态变更由精确 `project_id` 加全指纹授权，而非前缀标签查询。
- 短哈希碰撞由指纹不匹配检测，并在变更前失败；不同工作区永不共享容器、网络或命名卷。允许共享不可变 daemon 镜像缓存。
- 工作区移动创建新实体。带不同工作区 ID 但匹配仓库前缀的资源必须带恢复方向报告，且永不被自动接管/停止。
- Compose 仅通过 stdin 接收已验证的已提交 YAML 字节，以及由 `project_id` 推导的项目目录。测试扫描每个 Docker/Compose 标签，并拒绝任何资源元数据中的原始或规范工作区路径。
- 普通 down 移除容器/孤儿与临时网络，保留全部命名卷，且永不使用 prune。

## 实体：LifecycleLock

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `key` | string | 仅项目 ID |
| `mechanism` | enum | POSIX 咨询锁（advisory lock）`fcntl.flock` |
| `mode` | enum | 非阻塞排他 |
| `holder_operation` | enum | `dev` 或 `dev-down` |
| `acquired_at` | monotonic timestamp | 仅内部计时 |
| `storage_safety` | invariant | 安全每用户基目录、不跟随 symlink、当前用户 0600 常规文件 |

**状态转换**：

```text
available ── LOCK_EX|LOCK_NB success ──> held ── normal/exception/process exit ──> available
    └──── lock contention ─────────────> rejected(OPERATION_IN_PROGRESS)
```

空锁文件可保留；内核锁状态为权威。无需基于 PID 的陈旧恢复。

## 实体：LifecycleOperation

表示一次 `make dev` 或 `make dev-down` 运行。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `correlation_id` | UUID/string | 每个发出信封中的稳定生命周期运行关联 ID；每个信封另有唯一事件 ID |
| `action` | enum | `dev`、`dev-down` |
| `project_id` | string | 可安全展示 |
| `phase` | enum | `identity`、`lock`、`preflight`、`image-pull`、`image-verify`、`reconcile`、`liveness`、`readiness`、`stopping`、`final` |
| `status` | enum | `REQUESTED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`INTERRUPTED`、`REJECTED` |
| `started_at` | monotonic timestamp | 用于有界预算 |
| `readiness_started_at` | optional monotonic timestamp | 仅在全部镜像验证后设置 |
| `readiness_deadline` | optional monotonic timestamp | 恰好 start + 60 秒；状态协调、探针与重试使用剩余时间 |
| `duration_ms` | non-negative integer | 每阶段与合计 |
| `diagnostic_code` | stable enum | 来自 workflow event v2.0 |

**启动状态机**：

```text
REQUESTED
  └─ pure mode + identity/fingerprint + read-only manifest/runtime/config/port preflight valid
       └─ secure runtime directory/lock acquired + state revalidated
            ├─ endpoint/ownership/port drift ──> FAILED (no mutable action)
            └─ IMAGE PHASE
                 ├─ pull/digest failure ──> FAILED (no project instance created)
                 └─ IMAGES_AVAILABLE
                      └─ RECONCILING/STARTING
                           ├─ all live + authenticated ready ──> READY/SUCCEEDED
                           ├─ bounded wait ──> FAILED (resources retained)
                           └─ interrupt/runtime loss ──> INTERRUPTED (retriable)
```

**停止状态机**：

```text
REQUESTED ── identity/lock ──> DISCOVERING
  ├─ no exact-project container/network (volumes may remain) ──> SUCCEEDED (already stopped)
  └─ STOPPING ── graceful down ──> containers/network absent + volumes retained ──> SUCCEEDED
                  └─ timeout/runtime loss ──> FAILED (remaining state reported, volumes retained)
```

## 实体：DependencyInstance

项目中某一条定义的已观察、已状态协调状态。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `dependency_id` | enum | 必需依赖 |
| `container_id` | optional opaque ID | 从 Compose JSON 读取；未经项目/服务验证不得使用 |
| `image_digest` | OCI digest | 必须等于清单 index/选定平台身份 |
| `image_matches_desired` | boolean | 在所有者检查后，将观察到的精确 digest 与已验证的期望 index/当前平台 child 身份比较 |
| `state` | enum | `ABSENT`、`CREATED`、`RUNNING`、`STOPPING`、`EXITED`、`UNKNOWN` |
| `health` | enum | `UNKNOWN`、`STARTING`、`HEALTHY`、`UNHEALTHY` |
| `published_port` | integer | 必须匹配 URL 推导的主机端口 |
| `owner_labels_valid` | boolean | 变更/复用前必需 |
| `volume_attached` | boolean | 仅 PostgreSQL/Redis |

**状态协调**：

- 精确匹配的健康实例被复用。
- 缺失/已停止实例通过 `up` 收敛；忽略陈旧健康。
- 错误项目/指纹/所有者标签导致 `RESOURCE_OWNERSHIP_CONFLICT`；永不接管。
- 在期望 index/child 身份验证后，任何镜像不匹配期望身份的精确拥有的容器可由 Compose 替换，其声明的命名卷保留。无历史镜像允许列表或模糊的已评审/未知修订状态；所有权不匹配仍失败关闭。
- 健康的重复启动不得增加容器/网络/卷计数。

## 实体：DependencyHealthResult

一次探针的短生命周期验收证据。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `dependency` | enum | `postgres`、`redis`、`grafana` |
| `liveness` | enum | `alive`、`not_alive`、`unknown` |
| `readiness` | enum | `ready`、`not_ready`、`waiting` |
| `probe` | enum | `postgres-query`、`redis-auth-ping`、`grafana-health`、`grafana-admin` |
| `checked_at` | UTC timestamp | 仅作验收证据 |
| `duration_ms` | non-negative integer | 每次探针 |
| `code` | stable diagnostic | `OK` 或安全失败类别 |
| `safe_reason` | string | 有界、已脱敏，无原始依赖输出 |

**新鲜度规则**: 结果仅对其操作快照有效。新生命周期执行、容器重启/替换、daemon 重启或配置变更会使其失效。

## 实体：ComposeSecretMaterial

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `project_id` | string | 所有者键；非密钥值的一部分 |
| `purpose` | enum | `postgres-password`、`redis-config`、`grafana-admin-password`、`teardown-placeholder` |
| `source` | enum | 仅专用 Compose 子进程环境映射 |
| `container_file_mode` | octal | 通过 environment-source 密钥长语法为 0400 |
| `container_owner` | UID/GID | 固定镜像清单中的已验证非 root 值 |
| `source_field` | config field name | 仅名称，从不为值 |
| `lifecycle` | enum | 映射引用仅限操作；Compose 挂载文件仅随其容器存在 |
| `cleanup_state` | enum | `in-memory`、`released`、`container-removed` |

密钥字节被排除在相等比较、repr、异常、事件序列化、测试快照与诊断日志之外。它们从不是服务环境变量、命令参数、主机文件、命名卷或镜像层。Teardown 占位符匹配语法但不是可用凭据。

## 实体：LocalPersistentData

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `owner_project_id` | string | 项目作用域 |
| `dependency` | enum | PostgreSQL 或 Redis |
| `volume_id` | safe logical name | 经 Compose 项目作用域推导 |
| `durability` | enum | PostgreSQL `durable-fact`；Redis `preserved-rebuildable` |
| `schema_owner` | enum | PostgreSQL 为 API/Billing 迁移；Redis 无 |
| `deletion_policy` | enum | `not-supported-by-sf02` |

SF02 不创建业务表、不应用 Alembic 修订、不 seed 数据、不在既有卷上更改角色密码，且不定义面向开发者的公共破坏性清理操作。

## 实体：ServiceReadinessResult

API/Billing 运维响应投影。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `service` | enum | `api-service`、`billing-service` |
| `status` | enum | `ready`、`not_ready` |
| `version` | string | 既有 SF01 字段 |
| `request_id` | string | 既有关联字段 |
| `dependencies` | list | 仅出现在 503 响应；SF02 中恰好一个 PostgreSQL 结果 |
| `http_status` | enum | 就绪时 200，未就绪时 503 |

Liveness 是独立结果，且永不评估本实体。失败结果仅含 `name=postgres`、`status=not_ready` 与稳定安全码；永不包含 URL、用户名、数据库异常、SQL 或密码。

## 实体：ServiceReadinessMetrics

每个 API/Billing 进程拥有其 PostgreSQL 就绪检查探针行为的内存 Prometheus 投影。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `tokenmarket_postgres_readiness_probes_total` | monotonic counter | 每次完成的就绪检查探针尝试递增一次 |
| `tokenmarket_postgres_readiness_probe_failures_total` | monotonic counter | 每次 invalid-config、连接、认证、查询或超时结果递增一次 |
| `tokenmarket_postgres_readiness_probe_duration_seconds` | histogram | 观察每次完成的探针耗时（含失败），使用仓库批准的有界桶 |

指标不含 URL、用户名、数据库、异常、SQL、密码、工作区或其他无界标签。恢复时递增总计数但不递增失败计数，并产生新的耗时观察。

## 实体：WorkflowEvent v2.0

对严格 SF01 v1 读取器的破坏性替换，仅在已文档化的消费者迁移门禁之后激活。

| 字段 | 类型 | 规则 |
|-------|------|-------|
| `event_id` | UUID | 每个发出信封唯一，包括同一生命周期运行中的多个步骤 |
| `event_type` | const | `workflow.step` |
| `schema_version` | const | `2.0.0` |
| `timestamp` | UTC date-time | RFC 3339 发出时间戳 |
| `producer` | const | `repository-workflow` |
| `correlation_id` | string | 同一命令中每个信封共享的生命周期运行标识 |
| `payload` | object | 严格 workflow-step payload；无附加字段 |
| `payload.action`, `payload.component`, `payload.phase` | existing semantics | 从 v1 根移入 v2 payload |
| `payload.dependency` | optional enum | 新增；三个依赖之一 |
| `payload.status` | enum | 既有值加 `WAITING` |
| `payload.code` | enum | 既有稳定码加 SF02 诊断类别 |
| `payload.duration_ms`, `payload.message` | existing semantics | 安全、有界、非密钥 |

事件在一个 `correlation_id` 内按发出顺序排序。机器定义的依赖生命周期阶段与依赖特定失败码要求 `payload.dependency`。`WAITING`/`PASSED` 使用 `payload.code=OK`；`FAILED`/`SKIPPED` 不得使用 `OK`；v1 宽松的 `STARTED` 码语义不被收窄。部分依赖成功永不使聚合为 `PASSED`。

## 数据、迁移、备份与删除决策

- **业务 schema**: 不新增也不变更。
- **Alembic**: 不被 `dev`/`dev-down` 调用；既有迁移所有者规则保持不变。
- **事务/幂等**: 生命周期状态变更由锁串行化，并由精确项目身份做状态协调；不存在跨越 Docker 操作的数据库事务。
- **备份/恢复**: SF02 不备份本地数据。普通 down 保留 PostgreSQL 卷；恢复是重试/状态协调，而非隐式 restore。
- **删除**: 无面向开发者的破坏性操作。测试夹具仅可在 teardown 期间删除其自有的带测试标签的可丢弃资源。
- **状态协调**: 当前 Docker `ps/inspect` 快照与认证探针覆盖缓存/陈旧健康验收证据。
