# 任务：本地依赖环境生命周期

**输入**: 设计文档来自 `/specs/002-local-dependency-lifecycle/`

**前置条件**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**测试**: 每次行为变更**必须**编写测试，并在对应实现任务之前观察到失败。仅文档任务须写明具体校验目标。

**组织方式**: 任务按用户故事分组。US1 与 US2 均为 P1；全部实现保持在 SF01 失败关闭（fail-closed）激活门禁之后，直至消费者迁移、必需文档、可访问性/安全/脏工作区门禁，以及双平台生命周期/持久化/恢复/性能验收证据通过，之后两个公共 Make 入口、event v2 与帮助/恢复文本原子激活。

## 格式：`[ID] [P?] [Story] Description`

- **[P]**: 可并行，因变更不同文件，且不依赖同批中另一未完成任务
- **[Story]**: 映射到 `spec.md` 中的用户故事 1、2 或 3
- 每个任务命名其变更或校验的精确文件

## Phase 1: 准备（契约与供应链物化）

**目的**: 在实现行为前，确立已评审架构决策、版本化公共契约、不可变依赖事实与已锁定工作流包。

- [X] T001 将 ADR 002 接受为已批准的实现前设计，同时将实现验证标为 Pending，并在 `docs/decisions/002-local-compose-lifecycle.md` 中记录所有权、失败模式、双平台激活门禁、保留卷回滚与无清理边界
- [X] T002 [P] 通过将已评审功能契约复制到 `shared/contracts/local-environment/v1/lifecycle.md` 与 `shared/contracts/local-environment/v1/local-dependency-manifest.schema.json` 物化生命周期 v1
- [X] T003 [P] 物化 Root Make Workflow/event v2 所需标准信封与严格 workflow-step payload，且不修改 v1 Make/event 产物，文件为 `shared/contracts/repository-workflow/v2/make-workflow.md` 与 `shared/contracts/repository-workflow/v2/workflow-event.schema.json`
- [X] T004 [P] 在 `shared/contracts/repository-workflow/v1/service-health.openapi.yaml` 发布健康契约 v1.1：仅 API/Billing 的 PostgreSQL 503 就绪检查形状，200/liveness 形状不变
- [X] T005 解析官方 PostgreSQL 15.18、Redis 7.2.14 与 Grafana 13.0.3 的 OCI index 及 linux/amd64、linux/arm64 child digest，校验发布者/运行时 UID/GID/许可证/扫描事实，并提交到 `ops/workflow/local-dependencies.json`、`ops/workflow/toolchains.json` 与 `docs/decisions/002-local-compose-lifecycle.md`
- [X] T006 [P] 在 `tools/workflow/pyproject.toml` 与 `tools/workflow/uv.lock` 中添加 `workflow.local_env` 包发现与已评审 asyncpg 0.30.x 依赖，且不改服务锁
- [X] T007 在 `shared/contracts/README.md` 登记生命周期 v1、workflow v2、健康 1.1 次要更新、所有权、兼容性与弃用状态

---

## Phase 2: 基础（阻塞性前置）

**目的**: 构建跨故事的契约、事件、身份、锁与隔离测试基础，任何生命周期故事实现前必须完成。

**关键**: 本阶段通过前不得开始用户故事实现。T008–T013 先编写，且必须对预期缺失行为失败，之后才实现 T014–T018。

- [X] T008 [P] 在 `tests/workflow/test_contracts.py` 添加契约副本、schema 版本、不可变 v1 `make-workflow.md`/`workflow-event.schema.json`、health-1.1 次要兼容与契约目录漂移测试
- [X] T009 [P] 在 `tests/workflow/test_local_env_events.py` 添加 workflow event v2 测试：唯一事件 ID、稳定 type/version/producer、UTC 时间戳、生命周期关联、严格 payload、dependency 字段、WAITING 状态、诊断码、排序、脱敏与严格消费者迁移
- [X] T010 [P] 在 `tests/workflow/test_local_dependency_manifest.py` 添加清单测试：拒绝占位/仅 tag/仅 leaf digest、缺失平台 child、额外依赖、不安全运行时、非法 UID/GID 与超时漂移
- [X] T011 [P] 在 `tests/workflow/test_local_env_models.py` 添加类型化状态机与序列化排除测试：清单、操作、依赖、健康、密钥与就绪检查实体
- [X] T012 [P] 在 `tests/workflow/test_local_env_identity.py` 添加规范路径、NFC/UTF-8 哈希、空格/非 ASCII/symlink、短哈希碰撞、安全运行时目录、锁文件安全、争用与异常持有者退出测试
- [X] T013 [P] 在 `tests/workflow/test_sf02_transition.py` 用显式 v2 消费者迁移与激活门禁替换仅过渡断言，使公共 dev/dev-down 在全部必需能力具备前保持 `SF02_NOT_READY`
- [X] T014 [P] 在 `tools/workflow/local_env/__init__.py` 与 `tools/workflow/local_env/models.py` 实现不可变类型化实体、清单加载、恰好三依赖校验、安全 repr/相等行为与生命周期状态转换
- [X] T015 [P] 在 `tools/workflow/events.py` 实现 workflow event v2 标准信封发出：UUID 事件 ID、稳定 type/version/producer、UTC 时间戳、生命周期关联 ID、严格依赖 payload、WAITING 语义、稳定 SF02 诊断、有界消息与值脱敏，同时保留 v1 历史
- [X] T016 将每个仓库拥有的 JSONL 读取器与夹具断言迁移到 event v2 标准信封，并在 `tests/workflow/helpers.py`、`tests/workflow/test_events.py` 与 `tests/workflow/test_command_contract.py` 保留显式 v1 Make/event 回归覆盖
- [X] T017 在 `tools/workflow/local_env/identity.py` 实现规范物理路径身份、全指纹所有权、安全每用户运行时/项目目录、无 symlink 的 0600 锁文件与非阻塞 `fcntl` 加锁
- [X] T018 在 `tests/workflow/conftest.py` 创建合成密钥、临时工作区、单调时钟、假子进程与仅测试项目标签工厂，且永远不能指向开发者项目

**检查点**: 版本化契约校验通过，v1 回归覆盖保持绿灯，event v2 消费者已迁移，不安全清单失败关闭，身份/锁行为在无 Docker 时通过。

---

## Phase 3: 用户故事 1 - 一次启动并确认依赖真正可用 (Priority: P1) MVP 开发切片

**目标**: 从已校验本地配置状态协调恰好 PostgreSQL、Redis 与 Grafana，并在单一有界截止时间内返回即时认证的逐依赖就绪检查。

**独立测试**: 在受支持本地运行时上，对隔离测试项目用合法被忽略配置调用受保护的生命周期启动适配器；验证缺失的不可变镜像被拉取并单独报告，三个认证探针在 60 秒内通过，健康重复在 15 秒内完成且无资源增长或 registry 访问，每次失败保留可检查状态。公共激活仍由 US2、US3 与最终跨平台发布验收证据门控。

### 用户故事 1 的测试（先写并观察失败）

- [X] T019 [P] [US1] 在 `tests/workflow/test_local_env_config.py` 添加严格 `.env.local` 解析、mode 来源、URL 语法、回环、占位、百分号解码、合成密钥、重复端口、推导连接与仅字段名错误测试
- [X] T020 [P] [US1] 在 `infra/tests/test_local_compose.py` 添加 Compose 结构测试：恰好三个 index-digest 镜像、规范服务、回环长语法端口、隔离网络、PostgreSQL/Redis 命名卷、Grafana 0700 tmpfs、非 root 用户、0400 environment-source 密钥、认证 healthcheck、优雅期与禁止形态
- [X] T021 [P] [US1] 在 `tests/workflow/test_local_env_compose.py` 添加假 CLI 测试：固定 Compose 参数顺序、经 stdin 的已验证 YAML 字节、安全项目目录、本地端点/平台/能力检查、pull-missing/up-never 顺序、JSON 解析、所有权检查、端口竞态、中断与已脱敏错误
- [X] T022 [P] [US1] 在 `tests/workflow/test_local_env_lifecycle.py` 添加生命周期测试：只读前置检查顺序、锁内再校验、分离拉取计时、一个不可延长 60 秒截止时间、并发探针、健康快速路径、部分失败保留、超时边缘、重试收敛与聚合失败语义
- [X] T023 [P] [US1] 在 `tests/workflow/test_local_env_probes.py` 添加有界探针测试：PostgreSQL 认证 `SELECT 1`、同一连接 Redis AUTH/PING、Grafana health/admin 身份、剩余时间截断、陈旧结果拒绝、恢复与安全诊断映射
- [X] T024 [P] [US1] 在 `tests/workflow/test_local_env_security.py` 与 `tests/workflow/test_accessibility_performance.py` 添加安全与终端可访问性测试：证明 mode/配置拒绝先于协调或 Docker 访问，密钥/路径/原始输出永不进入不安全面，新纯文本/JSONL 输出保持 `NO_COLOR`、屏幕阅读器、非交互、无图标且退出状态可理解
- [X] T025 [P] [US1] 在 `tests/workflow/test_local_env_integration.py` 与 `tests/workflow/test_local_env_performance.py` 添加隔离真实 Compose 与确定性共享测试框架（harness）测试：冷启动、分离缺失镜像计时、预先声明 20 次批、十次健康重复、动态回环端口、认证主机/项目网络探针、错误认证、端口冲突/竞态、已停止/陈旧/部分状态、daemon 丢失、超时与保留失败状态

### 用户故事 1 的实现

- [X] T026 [P] [US1] 在 `tools/workflow/local_env/config.py` 实现纯 mode 优先的 `.env.local` 解析、严格本地 URL/密钥校验、两两端口检查、安全展示端点与推导容器连接
- [X] T027 [P] [US1] 在 `infra/docker/compose.local.yml` 定义恰好 PostgreSQL、Redis 与 Grafana：已评审 digest 引用、规范 DNS、回环发布、项目网络、声明存储、非 root 密钥文件、认证 healthcheck 与 60/30/30 优雅期
- [X] T028 [US1] 在 `tools/workflow/local_env/compose.py` 实现本地运行时与 Compose 适配器：已提交 blob 校验、stdin 传输、固定安全参数、捕获 JSON 状态、发布者/所有者检查、仅缺失拉取、当前平台 digest 校验与有界子进程终止
- [X] T029 [P] [US1] 在 `tools/workflow/local_env/probes.py` 实现有界 PostgreSQL、Redis 与 Grafana 认证探针：即时验收证据、安全类别与截止感知重试
- [X] T030 [US1] 在 `tools/workflow/local_env/compose.py` 实现仅子进程的 Compose 密钥映射、PostgreSQL/Grafana 密码文件、可注入安全的单指令 Redis 配置、已验证文件所有权/模式与仅解析 teardown 占位
- [X] T031 [US1] 在 `tools/workflow/local_env/lifecycle.py` 实现启动编排：从只读前置检查经锁/再校验、镜像拉取/校验、状态协调、并发即时探针、标准信封/纯文本聚合、保留资源的失败与幂等重试
- [X] T032 [US1] 在 `tools/workflow/cli.py` 添加内部受保护的 dev 分发路径，在测试中演练新的生命周期，但在激活门禁通过前保持公共 v1 `SF02_NOT_READY` 行为
- [X] T033 [P] [US1] 在 `.env.example` 声明 MODE、DATABASE_URL、REDIS_URL、GRAFANA_URL 与 GRAFANA_ADMIN_PASSWORD：分类、仅本地意图、URL 推导端口规则与不可用占位
- [X] T034 [P] [US1] 在 `infra/docker/README.md` 记录恰好三服务 Compose 模型、不可变镜像策略、回环/网络地址、持久化等级、密钥传输与无业务服务边界
- [X] T035 [US1] 在 `tests/workflow/conftest.py` 实现可丢弃真实 Compose 夹具与跨平台共享测试框架（harness）：动态端口、合成凭据/数据、精确测试标签、预先声明试验记账、经 stdin 的项目网络探针输入与仅夹具 teardown 护栏

**检查点**: 启动适配器通过 US1 单元、契约、安全、假子进程与真实依赖测试，同时公共激活门禁仍失败关闭。

---

## Phase 4: 用户故事 2 - 非破坏性停止并安全恢复 (Priority: P1) 受保护发布候选切片

**目标**: 在无配置密钥的情况下仅停止精确工作区项目，保留命名卷与 PostgreSQL 事实，从部分/中断状态恢复，串行化冲突，并在最终发布门禁前完成受保护双目标候选而不激活公共生命周期。

**独立测试**: 启动隔离环境，写入 PostgreSQL 标记，在 `.env.local` 不可用时运行 dev-down 两次，重启，并重复十个周期；验证标记保留、Redis 可为空、无重复/孤儿资源、Grafana 无匿名卷、无无关项目变更，且 100 次冲突操作产生安全可重试结果。

### 用户故事 2 的测试（先写并观察失败）

- [X] T036 [P] [US2] 在 `tests/workflow/test_local_env_identity.py` 与 `tests/workflow/test_local_env_dirty_worktree.py` 扩展所有权与工作区保留测试：同路径稳定、分支独立、不同 clone/worktree 隔离、移动检测、仅报告旧资源、全指纹碰撞失败、无路径标签，以及跨 dev/dev-down 脏已跟踪/未跟踪/symlink 文件不变
- [X] T037 [P] [US2] 在 `tests/workflow/test_local_env_compose_down.py` 添加假 Compose down 测试：缺失配置、仅解析密钥、精确项目/指纹授权、已停止仅卷状态、已停止容器、孤儿网络、`down --remove-orphans`、75 秒边界、禁止 volume/image/prune 标志与精确标签回退
- [X] T038 [P] [US2] 在 `tests/workflow/test_local_env_down.py` 添加生命周期 down 测试：身份先于配置、立即加锁、优雅停止校验、重复成功、命名卷保留、部分失败、重试、工作区移动报告与安全最终事件
- [X] T039 [P] [US2] 在 `tests/workflow/test_local_env_concurrency.py` 添加 100 次重复启动/start-vs-down 争用、锁持有者中断、端口竞态、无重复资源、无卷删除与可重试失败者测试
- [X] T040 [P] [US2] 在 `tests/workflow/test_local_env_persistence.py` 添加十次 start/down/restart 循环测试：PostgreSQL 标记保留、空 Redis 容忍、稳定卷身份、无孤儿网络、无 Grafana 匿名卷，且无 schema/迁移/seed 动作
- [X] T041 [P] [US2] 在 `tests/workflow/test_local_env_recovery.py` 添加恢复测试：已停止/不健康容器、daemon 丢失、SIGINT、失败 down、陈旧健康、错误持久化 PostgreSQL 凭据，以及无隐式清理或角色变更的直接收敛

### 用户故事 2 的实现

- [X] T042 [P] [US2] 在 `tools/workflow/local_env/identity.py` 扩展身份发现与变更授权：精确项目/全指纹检查、碰撞失败、无路径标签与强制仅报告的工作区移动发现
- [X] T043 [US2] 在 `tools/workflow/local_env/compose.py` 实现无配置的精确项目 down、仅解析密钥解析、有界优雅停止、状态/卷校验，以及无 volume、镜像或前缀级移除的精确标签容器/网络回退
- [X] T044 [US2] 在 `tools/workflow/local_env/lifecycle.py` 实现 dev-down 编排、已停止幂等、命名卷保留、工作区移动指引、安全失败保留与最终逐依赖事件
- [X] T045 [US2] 在 `tools/workflow/local_env/lifecycle.py` 实现中断启动/停止、已停止/陈旧/部分精确拥有的资源、带卷保留的期望镜像替换、daemon 恢复，以及无隐式变更的凭据漂移失败的状态协调
- [X] T046 [US2] 在 `tools/workflow/local_env/lifecycle.py` 对每个可变阶段与最终事件强制一把锁，使失败的重复/冲突操作返回 `OPERATION_IN_PROGRESS`，且无拉取、探针、资源或卷副作用
- [X] T047 [US2] 在 `Makefile` 保留根目标名称与 mode 转发，同时准备激活就绪的帮助、副作用、保留与恢复文本，直至最终原子切换前保持 Pending
- [X] T048 [US2] 在 `tests/workflow/conftest.py` 添加受保护的故障注入、进程中断、资源计数、标记保留、Redis 重置与精确测试项目清理辅助，且不能选择开发者项目
- [X] T049 [US2] 在 T042–T048 通过后，在既有失败关闭护栏后完成激活候选 event-v2 与真实 dev/dev-down 分发，且不移除公共运行时 `SF02_NOT_READY`，文件为 `tools/workflow/cli.py`

**检查点**: 两个 P1 激活候选故事经受保护适配器通过；启动与停止幂等、串行、非破坏、隔离且可安全恢复，同时公共 Make 入口仍以 `SF02_NOT_READY` 失败关闭。

---

## Phase 5: 用户故事 3 - 使用稳定地址连接并诊断不可用状态 (Priority: P2)

**目标**: 仅向 API Service 与 Billing Service 提供一套主机/容器连接契约与依赖感知就绪检查，不改变 liveness、Gateway/Admin 行为，也不启动业务服务。

**独立测试**: 校验三个依赖的主机与规范项目网络认证连接，然后独立用可注入探针运行 API 与 Billing；PostgreSQL 中断必须使 liveness 保持 200，就绪检查在两秒内返回精确安全 503 响应，并在无服务重启时恢复到未变的 200 形状。

### 用户故事 3 的测试（先写并观察失败）

- [X] T050 [P] [US3] 在 `tests/workflow/test_local_env_connections.py` 添加测试：主机 URL 仍为唯一事实，容器 URL 仅将 host/port 替换为 postgres/redis/grafana，安全输出去除 user-info，且不存在竞争端口/容器 URL 字段
- [X] T051 [P] [US3] 在 `tests/workflow/test_local_env_connectivity.py` 添加项目网络集成测试：执行真实 PostgreSQL 查询、Redis AUTH/PING 与 Grafana health/admin HTTP 请求，而非仅 DNS 检查
- [X] T052 [P] [US3] 在 `services/api-service/tests/test_health.py` 与 `services/api-service/tests/test_readiness_metrics.py` 添加 API Service 契约与可观测性测试：未变 liveness/ready-200 形状、精确安全 503 依赖形状、request ID、invalid-config/auth/query/timeout 映射、无重启恢复、探针总数/失败计数、耗时直方图与无密钥有界标签
- [X] T053 [P] [US3] 在 `services/api-service/tests/test_database_readiness.py` 添加 API Service 数据库测试：安全 URL 驱动映射、生命周期拥有的 engine、`pool_pre_ping`、有界 async `SELECT 1`、无重试、关闭 dispose 与真实 PostgreSQL 恢复
- [X] T054 [P] [US3] 在 `services/billing-service/tests/test_health.py` 与 `services/billing-service/tests/test_readiness_metrics.py` 添加 Billing Service 契约与可观测性测试：未变 liveness/ready-200 形状、精确安全 503 依赖形状、request ID、invalid-config/auth/query/timeout 映射、无重启恢复、探针总数/失败计数、耗时直方图与无密钥有界标签
- [X] T055 [P] [US3] 在 `services/billing-service/tests/test_database_readiness.py` 添加 Billing Service 数据库测试：安全 URL 驱动映射、生命周期拥有的 engine、`pool_pre_ping`、有界 async `SELECT 1`、无重试、关闭 dispose 与真实 PostgreSQL 恢复
- [X] T056 [P] [US3] 在 `tests/workflow/test_boundaries.py` 添加边界断言：Gateway/Admin 不获得依赖探针、dev 不启动业务服务，且不引入业务路由/schema/迁移/seed 行为

### 用户故事 3 的实现

- [X] T057 [US3] 在 `tools/workflow/local_env/config.py` 与 `tools/workflow/local_env/lifecycle.py` 从已校验连接投影发出匹配的已脱敏主机端点与规范容器地址，且不序列化凭据
- [X] T058 [P] [US3] 在 `services/api-service/app/database.py` 实现 API Service 自有的两秒 async PostgreSQL `SELECT 1` 探针、SQLAlchemy engine 工厂、安全错误类别与关闭 dispose
- [X] T059 [US3] 在 `services/api-service/app/main.py`、`services/api-service/app/health.py` 与 `services/api-service/app/observability.py` 经 lifespan/application state 接线 API 探针，保持 `/health/live` 独立，保留 ready-200 形状，仅返回契约化的 PostgreSQL 503 结果，并记录安全探针总数/失败/耗时指标
- [X] T060 [P] [US3] 在 `services/billing-service/app/database.py` 实现 Billing Service 自有的两秒 async PostgreSQL `SELECT 1` 探针、SQLAlchemy engine 工厂、安全错误类别与关闭 dispose
- [X] T061 [US3] 在 `services/billing-service/app/main.py`、`services/billing-service/app/health.py` 与 `services/billing-service/app/observability.py` 经 lifespan/application state 接线 Billing 探针，保持 `/health/live` 独立，保留 ready-200 形状，仅返回契约化的 PostgreSQL 503 结果，并记录安全探针总数/失败/耗时指标
- [X] T062 [P] [US3] 在 `services/api-service/tests/conftest.py` 实现隔离假探针与真实 PostgreSQL 夹具用于 API 就绪检查，且不暴露 URL 或异常正文
- [X] T063 [P] [US3] 在 `services/billing-service/tests/conftest.py` 实现隔离假探针与真实 PostgreSQL 夹具用于 Billing 就绪检查，且不暴露 URL 或异常正文
- [X] T064 [P] [US3] 在 `services/api-service/README.md` 与 `services/billing-service/README.md` 记录独立服务启动、PostgreSQL liveness/就绪检查语义、两秒边界、恢复与无生命周期管理边界

**检查点**: 容器/主机连接契约通过；API 与 Billing 独立恢复就绪检查；liveness、Gateway、Admin 与 dev 依赖集保持不变。

---

## Phase 6: 打磨与跨切面发布验收证据

**目的**: 完成安全操作指引、全局质量门禁、跨平台性能验收证据、易用性校验，以及上线/回滚可追踪性。

- [X] T065 [P] 在 `ops/runbooks/local-environment.md` 编写仓库工作流负责人诊断、安全检查、端口/认证/运行时/超时/凭据漂移恢复、工作区移动、中断、持久化、可访问性、验收证据所有权与非破坏性停止流程
- [X] T066 [P] 在 `README.md`、`ops/README.md` 与 `CLAUDE.md` 更新开发者导航、前置条件、根工作流效果、受支持平台、服务名、安全地址与 SF02/SF19 范围边界
- [X] T067 在 `tests/workflow/test_secret_scan.py`、`tests/workflow/test_dependency_scans.py`、`tests/workflow/test_local_env_dirty_worktree.py`、`tests/workflow/test_accessibility_performance.py` 与 `tests/workflow/test_boundaries.py` 添加最终负向断言：密钥/路径泄露、远程/通配端点、不安全依赖身份、运行时锁文件变更、包发现漂移、脏已跟踪/未跟踪工作区变更、不可访问终端输出、禁止清理/迁移与无关资源变更
- [X] T068 通过 `Makefile` 运行格式化、lint、type-check、契约漂移、单元/契约/集成/恢复、可访问性、脏工作区、就绪检查指标、密钥/依赖/容器扫描、覆盖率、构建与迁移无变更门禁，并将已脱敏命令结果记录在 `specs/002-local-dependency-lifecycle/evidence/quality-gates.md`
- [X] T069 在 Linux x86_64 上执行已提交的共享测试框架（harness）：20 次冷启动至少 19 次在 60 秒内、十次重复在 15 秒内、十次持久化循环、原生镜像身份、信号/恢复与标准 event-v2 信封检查，将环境与汇总验收证据记录在 `specs/002-local-dependency-lifecycle/evidence/linux-amd64.md`
- [X] T070 在 macOS arm64 上执行同一已提交的测试框架：原生镜像身份、NFC/路径行为、Docker Desktop 回环、密钥所有权、stop 信号、20 次冷启动、十次重复、持久化与标准信封对等，将环境与汇总验收证据记录在 `specs/002-local-dependency-lifecycle/evidence/macos-arm64.md`
- [X] T071 由仓库工作流负责人对合格的首次 SF02 参与者运行已提交的、仅基于文档的十人易用性验证协议，要求至少九人在十分钟内完成准备、启动、状态确认与恢复发现，且仅将汇总已脱敏验收证据记录在 `specs/002-local-dependency-lifecycle/evidence/developer-usability.md`
- [X] T072 执行 `specs/002-local-dependency-lifecycle/quickstart.md` 中每个安全场景，并创建链接质量、平台、持久化、就绪检查、安全与易用性结果的已脱敏验收证据索引于 `specs/002-local-dependency-lifecycle/evidence/README.md`
- [X] T073 在 `docs/decisions/002-local-compose-lifecycle.md` 与 `specs/002-local-dependency-lifecycle/quickstart.md` 定稿需求到测试的需求追踪关系、依赖/安全/schema 影响、激活/弃用通知、不可变产物身份、保留卷回滚决策点与验收证据链接，同时将 ADR 实现验证保持为 Pending
- [X] T074 仅在 T065–T073 与双平台验收证据通过后，原子移除运行时 `SF02_NOT_READY`，使真实 dev/dev-down 与 event v2 成为默认，发布匹配的帮助/恢复文本，并在 `tools/workflow/cli.py`、`Makefile` 与 `docs/decisions/002-local-compose-lifecycle.md` 将 ADR 实现验证标为 Verified

---

## 需求追踪关系

| 需求 | 实现与验收证据任务 |
|-------------|-----------------------------------|
| FR-001 | T001, T003, T013, T032, T047–T049, T065–T074 |
| FR-002 | T010, T020, T027, T031, T056, T067 |
| FR-003 | T005, T010, T021, T025, T027–T028, T069–T070 |
| FR-004 | T019, T021–T024, T026, T028, T031 |
| FR-005 | T019, T024, T026, T033, T050, T067 |
| FR-006 | T024, T033, T067 |
| FR-007 | T019–T020, T026–T027, T034, T050, T057, T064–T066 |
| FR-008 | T019, T026, T050, T057 |
| FR-009 | T020, T025, T027, T034, T051, T067, T069–T070 |
| FR-010 | T021–T022, T025, T028, T031, T039, T041 |
| FR-011 | T020, T023, T025, T027, T029, T051 |
| FR-012 | T020, T023, T025, T027, T029, T051 |
| FR-013 | T009, T022, T025, T029, T031, T069–T070 |
| FR-014 | T022, T025, T031, T039, T069–T070 |
| FR-015 | T022, T025, T031, T041, T045, T065 |
| FR-016 | T012, T017, T021, T024, T028, T036, T042, T067, T069–T070 |
| FR-017 | T037–T040, T043–T044, T047–T048 |
| FR-018 | T037–T038, T043–T044 |
| FR-019 | T036, T038, T041–T042, T044, T065 |
| FR-020 | T020, T037, T040–T045, T048, T067, T069–T070 |
| FR-021 | T020, T040, T044, T048, T069–T070 |
| FR-022 | T020, T024, T037, T040, T043, T067 |
| FR-023 | T012, T017, T039, T041, T046, T048 |
| FR-024 | T034, T047, T064–T066, T071–T072 |
| FR-025 | T004, T008, T052–T064 |
| FR-026 | T003, T007, T009, T013, T015–T016, T022, T031, T038, T044, T047, T049, T069–T070, T074 |
| FR-027 | T006, T021, T024, T028, T040, T056, T067–T068 |
| FR-028 | T012, T017, T024, T028, T036, T042, T066–T070 |
| FR-029 | T005, T010, T021, T028, T066, T069–T070, T074 |
| ER-001 | T001–T009, T013–T016, T049, T073–T074 |
| ER-002 | T018–T020, T024, T026–T030, T033, T037, T052–T063, T067–T070 |
| ER-003 | T036–T049, T067, T069–T070 |
| ER-004 | T022, T025, T035, T039–T040, T053, T055, T069–T070 |
| ER-005 | T011–T012, T017, T022–T023, T031, T037–T046 |
| ER-006 | T009, T015, T022, T031, T038, T044, T052, T054, T059, T061, T065, T068–T070 |
| ER-007 | T024, T047, T065–T071 |
| SC-001 | T025, T035, T069–T070 |
| SC-002 | T022, T025, T039, T069–T070 |
| SC-003 | T040, T048, T069–T070 |
| SC-004 | T019, T021–T025, T037–T041, T052–T055, T067 |
| SC-005 | T019, T025, T034, T050–T051, T057, T064–T066, T069–T070 |
| SC-006 | T038–T049, T069–T070 |
| SC-007 | T009, T015, T024, T052–T063, T067–T070 |
| SC-008 | T047, T065–T066, T071–T072 |
| SC-009 | T012, T017, T039, T041, T046, T048, T069–T070 |

每个故事检查点使用本矩阵验证实现与必需验收证据仍保持关联；T073 将已完成行转换为 PR/发布验收证据，而非首次创建追踪关系。

---

## 依赖与执行顺序

### 阶段依赖

- **Phase 1（准备）**: 立即开始。T002、T003、T004 与 T006 可并行；T005 需要 T001 的 ADR 所有权上下文；T007 跟在契约副本之后。
- **Phase 2（基础）**: 依赖 Phase 1。T008–T013 为失败测试批；T014–T018 实现共享契约/事件/模型/身份/测试基础并阻塞全部故事代码。
- **Phase 3（US1）**: 依赖 Phase 2。T019–T025 必须在 T026–T035 前失败。US1 经受保护生命周期适配器可独立测试，但尚未改变公共 v1 行为。
- **Phase 4（US2）**: 依赖 T026–T035 中的共享 US1 适配器。T036–T041 必须在 T042–T049 前失败。T049 仅完成受保护激活候选；公共激活在 T074 前仍禁止。
- **Phase 5（US3）**: 假探针服务工作可在 Phase 2 后开始；T051 与 T053/T055 的真实 PostgreSQL 部分依赖 P1 环境。在两个 P1 故事之后完成 US3 以保持优先级顺序。
- **Phase 6（打磨）**: 依赖全部选定故事。平台、易用性与发布验收证据需要完整实现与全部自动化门禁。

### 用户故事依赖图

```text
准备 -> 基础 -> US1 启动核心 -> US2 受保护生命周期候选 -> US3 连通性/就绪检查 -> 发布验收证据 + 原子激活
                                  \-------------------------------------------> US3 假探针工作
```

### 用户故事依赖

- **US1 (P1)**: 实现与隔离测试仅依赖基础。有意保持在激活门禁之后。
- **US2 (P1)**: 复用 US1 的 Compose/生命周期核心，并证明计划要求的安全条件，同时将 US1+US2 留在失败关闭的公共门禁之后。
- **US3 (P2)**: 服务假探针行为在基础之后独立；完整连通性验收证据依赖 P1 本地环境。API 与 Billing 实现彼此独立。

### 每个用户故事内

- 先写该故事的测试任务，并确认对预期缺失行为失败。
- 在产生副作用的适配器之前实现纯校验与模型。
- 在编排与公共分发之前实现适配器/探针。
- 跨集成保持一个不可延长截止时间与一个精确所有权/锁边界。
- 在宣布故事完成前完成负向、恢复、安全与真实依赖验收证据。

## 并行执行示例

### 用户故事 1

```text
可并行失败测试批：T019 配置 | T020 Compose 结构 | T021 假 CLI | T023 探针 | T024 安全
上述测试后的可并行实现批：T026 配置 | T027 Compose 资产 | T029 探针 | T033 示例配置 | T034 infra 文档
然后串行集成：T028 -> T030 -> T031 -> T032 -> T035
```

### 用户故事 2

```text
可并行失败测试批：T036 身份/移动 | T037 Compose down | T038 生命周期 down | T039 并发 | T040 持久化 | T041 恢复
实现顺序：T042 -> T043 -> T044 -> T045 -> T046 -> T047 -> T048 -> T049
```

### 用户故事 3

```text
可并行失败测试批：T050 连接事实 | T051 网络探针 | T052-T053 API | T054-T055 Billing | T056 边界
可并行服务实现：T058 API 数据库 | T060 Billing 数据库
服务接线后的可并行集成夹具：T062 API 夹具 | T063 Billing 夹具 | T064 服务文档
```

## 实施策略

### MVP 开发切片

1. 完成准备与基础。
2. 完成 US1 至 T035，并独立校验启动适配器。
3. 保持公共 dev/dev-down 失败关闭；不交付仅启动的生命周期。

### P1 发布候选

1. 完成两个 P1 故事至 T049。
2. 校验持久化、隔离、脱敏、恢复、并发与 v2 消费者迁移。
3. 将 dev/dev-down 与 event v2 保持在运行时 `SF02_NOT_READY` 护栏之后。
4. 继续 P2 与共享跨平台发布门禁；仅 P1 候选不公开激活。

### 首次公开发布

1. 完成 US3、T065–T073，以及全部自动化、易用性、安全、脏工作区、持久化、恢复与性能门禁。
2. 从同一已提交的测试框架获得通过的 Linux amd64 与 macOS arm64 验收证据。
3. 在 T074 原子激活 dev/dev-down、event v2、帮助文本与 ADR 实现验证。

### 增量交付

1. 带不可变 v1 历史与 v2 迁移门禁的契约/供应链基础。
2. 门禁后的 US1 启动核心。
3. 作为受保护 P1 候选的 US2 安全停止。
4. US3 稳定连通性加独立 API/Billing 就绪检查。
5. 跨平台、易用性、安全与发布验收证据，随后单一原子公共激活。

## 说明

- `[P]` 仅标记文件互不重叠的工作；汇聚到 `compose.py`、`lifecycle.py`、`cli.py` 或共享测试夹具的任务有意串行。
- 仅测试 teardown 仅授权精确带测试标签的项目；无任务添加面向开发者的破坏性清理目标。
- 无任务将 Kafka/Redpanda、Prometheus、Loki、MinIO、frontend、Gateway、Admin 或业务服务启动加入 `make dev`。
- 无任务创建业务 schema、Alembic 修订、seed、生产/测试资源访问、主机密钥文件、服务环境密钥、匿名卷、通配绑定或远程 daemon 路径。
- 在每个任务或连贯测试优先对之后提交，保留 Conventional Commit 范围与 v2 激活门禁。

---

## Phase 7: 收敛

**目的**: 关闭 `/speckit-implement` 后发现的实现缺口——任务已标完成但代码或自动化验收证据仍仅部分满足 spec/plan。Phase 6 发布任务 T067–T074 仍开放，此处不重述。

- [X] T075 [P] 扩展并发覆盖超出串行 down：100 次重复 start/start 与 start-vs-down 争用、持锁中断、端口竞态失败者行为、无重复资源、无卷删除，以及副作用为零的可重试 `OPERATION_IN_PROGRESS` 失败者，文件为 `tests/workflow/test_local_env_concurrency.py`，必要时在 `tests/workflow/conftest.py` 使用假适配器接缝，依据 FR-023、SC-006、US2 独立测试（partial）
- [X] T076 添加真实 Compose 十周期 start/down/restart 持久化：证明已写 PostgreSQL 标记行保留、容忍 Redis 为空、卷身份稳定、无孤儿网络或 Grafana 匿名卷，且无 schema/迁移/seed，在 `tests/workflow/test_local_env_persistence.py` 使用 `RealComposeProjectFactory`，依据 US2/AC3、FR-020、FR-021、SC-003（partial）
- [X] T077 将 `start_local_environment` 与 `stop_local_environment` 期间的 `KeyboardInterrupt`/SIGINT 映射为 `OperationStatus.INTERRUPTED`，保留项目资源、安全已脱敏最终事件并释放锁，在 `tools/workflow/local_env/lifecycle.py`，依据 spec Edge Cases（中断信号）与 FR-015（missing）
- [X] T078 [P] 将 `tests/workflow/test_local_env_connectivity.py` 中的 `SF02_REAL_COMPOSE` 占位替换为经 `NetworkProbeRunner` 的认证项目网络探针：PostgreSQL `SELECT 1`、Redis AUTH/PING 与 Grafana health/admin HTTP（非仅 DNS），依据 US3/AC1、FR-011、FR-012、plan Phase D（partial）
- [X] T079 完成受保护的 T048 辅助：故障注入可中断持锁生命周期、资源计数仅反映精确 `tmtest-` 标签，且 PostgreSQL 标记/Redis 重置辅助可供持久化/恢复套件使用而不指向开发者项目，在 `tests/workflow/conftest.py`，依据 plan Phase D / T048（partial）
- [X] T080 添加恢复测试：演练 T077 中断路径、无变更的 daemon 丢失失败关闭诊断，以及中断后无隐式清理或角色变更的直接收敛，在 `tests/workflow/test_local_env_recovery.py`，依据 T041、FR-015、plan Phase D（partial）

---

## Phase 8: 收敛

**目的**: Phase 7 实现后的残留缺口。Phase 6 发布/激活任务 T068–T074 仍开放，不重述。

- [X] T081 [P] 完成残留 T067 负向：在 `tests/workflow/test_secret_scan.py`（或生命周期脱敏套件）中添加 SF02 生命周期事件/纯文本密钥与工作区路径泄露断言，并将 `tests/workflow/test_dependency_scans.py` 中 `assert True` 扫描器失败关闭桩替换为真实非零退出契约，依据 FR-006、Constitution II、T067（partial）
- [X] T082 完成 T077 残留：对任何需要它的诊断/记账使用返回的 `OperationStatus.INTERRUPTED` 转换（不得丢弃不可变结果），并添加 `start_local_environment` 的 KeyboardInterrupt 测试，证明资源保留、锁释放与安全最终事件，在 `tools/workflow/local_env/lifecycle.py` 与 `tests/workflow/test_local_env_recovery.py`（或生命周期测试），依据 Edge Cases（中断）、FR-015（partial）

## Phase 9: 收敛

**目的**: ADR 003 分层部署工作与 SF02 同树落地后发现的缺口。Phase 6 发布/激活任务 T069–T074 仍开放且**不**重述。先前收敛 Phase 7–8 已完成。

- [X] T083 针对 ADR 003 部署资产加固 SF02 隔离：保持 `compose.local.yml` 无应用服务；确保 `tests/workflow/test_boundaries.py` 及相关护栏仍禁止经 `make dev` 启动业务服务；在 `tests/workflow/test_sf02_transition.py` 允许被忽略的 `.env.test`/`.env.prod`（部署配置），且不削弱 `tools/workflow/cli.py` 中公共 `dev` 对 `.env.local` 的预配置 `SF02_NOT_READY` 顺序，依据 FR-001、FR-002、plan Notes（dev 上无业务服务启动）（unrequested）
- [X] T084 解决或正式记录 Node 精确版本漂移（`toolchains.json` 对主机），使根 `make toolchain-check` / `make build` 能在 T070/T074 前于 SF02 macOS arm64 验收证据主机上成功，仅在需要时更新 `ops/workflow/toolchains.json` 和/或 `specs/002-local-dependency-lifecycle/evidence/quality-gates.md`，依据 plan 质量门禁、FR-027、SC-001 主机就绪（partial）
- [X] T085 将声称生命周期适配器缺失的公共 `SF02_NOT_READY` 消息替换为激活门禁措辞（适配器已存在；双平台验收证据待定），在 `tools/workflow/cli.py` 以及 `Makefile` / `ops/runbooks/local-environment.md` 中匹配的帮助/运行手册字符串，依据 FR-001、FR-024、ER-006（partial）
