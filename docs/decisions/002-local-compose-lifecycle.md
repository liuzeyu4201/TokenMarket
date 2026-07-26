# ADR 002：通过 Docker Compose 实现本地依赖生命周期

**状态**：`Accepted`（已接受）
**实现验证**：`Verified`（已验证）（T074, 2026-07-25）— 双平台生命周期、质量门禁与负责人授权的易用性验收证据记录于 `specs/002-local-dependency-lifecycle/evidence/`。公共 `make dev` / `make dev-down` 与默认 event v2 已激活。
**Date**: 2026-07-15
**Owner**: TokenMarket Engineering
**Deciders**: Repository maintainers / Platform team

## 背景

SF02 必须用可复现的本地生命周期替换 SF01 的 `SF02_NOT_READY` 过渡，覆盖 PostgreSQL 15、Redis 7 与 Grafana。相同公共命令必须在 macOS arm64 与 Linux x86_64 上可用，隔离多个 clone/worktree，保留 PostgreSQL 数据，拒绝非本地配置，串行化并发操作，并在不泄露合成本地凭据的情况下暴露认证就绪检查。

仓库已拥有 Python 工作流工具、根 Make 契约、结构化工作流事件、配置脱敏，以及作为维护工具链的 Docker。引入独立编排 CLI 将重复这些控制。

## 决策

使用一份已提交的 Docker Compose 应用 `infra/docker/compose.local.yml`，仅通过既有 Python 工作流工具与根目标 `make dev`、`make dev-down` 调用。

适配器将：

1. 从规范工作区根推导 `tokenmarket-<12-hex-sha256>`，用完整 64 位十六进制指纹标记资源，短哈希碰撞时失败关闭（fail-closed），并将短 ID 显式作为 Compose 项目名传入。校验已提交 Compose blob，经 `-f -` 管道传入其字节，并使用仅由项目 ID 推导的 `0700` 项目目录，使 Compose 规范标签永不保留原始工作区路径。
2. 使用项目作用域的容器、网络与命名卷；永不设置固定 `container_name` 或全局卷名。
3. 消费版本化的本地依赖清单，其中包含 PostgreSQL、Redis 与 Grafana 的精确镜像 tag、多平台 OCI index digest 以及两个目标平台 child digest。
4. 仅拉取缺失的已声明 digest，然后启动一个覆盖 Compose 状态协调、状态收集与并发认证探针的 60 秒就绪检查截止时间，期间不再拉取。
5. 将发布端口仅绑定到 `127.0.0.1`；其取值与全部容器地址均由三个已校验主机 URL 推导。
6. 要求可注入安全的 `tm_local_` 凭据，仅传入专用 Compose 子映射，并使用 environment-source 密钥创建由每个已验证上游非 root UID/GID 拥有的 0400 文件；对全部子进程/事件失败脱敏。
7. 用每项目非阻塞 POSIX 咨询锁（advisory lock）串行化完整生命周期。
8. 在普通 down 时保留 PostgreSQL 与 Redis 命名卷；将 Grafana `/var/lib/grafana` 挂载为 tmpfs，使临时状态在 SF19 拥有仪表盘与数据源之前不创建匿名卷。
9. 将 Root Make/workflow event v2 发布为标准事件封装，含唯一事件 ID、稳定 type、schema version、UTC 时间戳、producer、生命周期关联 ID 与严格 workflow-step payload，并通过显式消费者迁移/弃用门禁，而非修改严格 v1 契约；翻译 Compose JSON 与认证探针，而不是把 Docker 输出暴露为 API。
10. 拒绝远程 Docker 端点，因主机锁与端口所有权检查无法保护远程 daemon。

选定依赖发布为 PostgreSQL `15.18-bookworm`、Redis `7.2.14-bookworm` 与 Grafana OSS `13.0.3`；实现变更必须在接受 Compose 资产前解析、校验、扫描并提交真实的多平台 index 与两个目标 child digest。

### 已解析依赖验收证据（verified 2026-07-16）

方法：每个 OCI index digest 计算为经两个独立镜像仓库镜像拉取的原始 index 文档的 SHA-256，并交叉校验相等；child digest 从 index manifest list 读取；linux/arm64 镜像在 darwin/arm64 上以 Docker 29.5.3 与 Compose v5.1.4 原生拉取并执行。规范机器可读值提交于 `ops/workflow/local-dependencies.json`。

- **PostgreSQL `15.18-bookworm`** (`docker.io/library/postgres`): index `sha256:b0c5bab0fbba8e0c221f73b1dc6359ec35f8650074377e727299df248fc8ad51`; linux/amd64 `sha256:fafb7480959eeeb7f1e43b479e642ffef2aa0f067242a1954ab41f2d764e2786`; linux/arm64 `sha256:92c67be3a884bc55d99e73dab0baca3f7a2c1591dc1828abadfdd640b10866c8`; runtime `uid=999 gid=999` (`postgres`); PostgreSQL License.
- **Redis `7.2.14-bookworm`** (`docker.io/library/redis`): index `sha256:f0707c78ea880b293ccdeb410c9c0a8ccae93fe7128799b751333a698b0a39a7`; linux/amd64 `sha256:86778a4a011a500d9a502858e27647380b62e5e8fbadef3f59e506f0899792fd`; linux/arm64 `sha256:7ee8f94475527b5d6a1077c2be9d7fab2b1417fe0d9985ffd28f29764c79c291`; runtime `uid=999 gid=999` (`redis`); BSD 3-Clause (final BSD-licensed Redis release line).
- **Grafana OSS `13.0.3`** (`docker.io/grafana/grafana`): index `sha256:1a345428a36270f5fb9add69fea71450a5843c15266c99359d6d380470ab19c9`; linux/amd64 `sha256:65f8af7bd56f4010036ca45ef301deae30bd102880926bfd48f8c19be85b6fd8`; linux/arm64 `sha256:d2ee7728138ac45709a1dde82eebadd85f9768eb46b528665f78426c606a35b5`; AGPL-3.0，以未修改本地容器使用，不提供分发或托管服务。上游以 `uid=472`、主组 `0`（root）运行；冻结清单 schema 要求 `runtime_gid >= 1`，且数据模型要求已验证非 root 运行时身份，因此 Compose 资产固定 `user: "472:472"` 与带 `uid=472,gid=472,mode=0700` 的 `/var/lib/grafana` tmpfs。已在 Docker 29.5.3 上验证 Grafana 13.0.3 在该 tmpfs 上以 `472:472` 启动，且 `GET /api/health` 返回 200 且 `database="ok"`；清单记录 `runtime_uid=472, runtime_gid=472`。

漏洞扫描（Trivy，严重级别 HIGH/CRITICAL，针对固定 digest，2026-07-16；扫描可从已提交 digest 复现，并在任一依赖变更时重跑）：

- PostgreSQL: 16 CRITICAL / 45 HIGH findings — 7 个唯一 CVE，均在 Debian bookworm userland（`perl` 5.36 CVE-2026-13221/42496/8376、`zlib1g` CVE-2023-45853、`libsqlite3-0` CVE-2025-7458、`libxml2` CVE-2026-6653）外加捆绑 Go 工具中的一个 Go `stdlib` CVE-2025-68121；均不在 PostgreSQL 服务器构建本身。
- Redis: 4 CRITICAL / 17 HIGH — 来自 bookworm 基座的 `perl-base` CVE-2026-13221/42496/8376 与 `zlib1g` CVE-2023-45853。
- Grafana: 0 CRITICAL / 32 HIGH。

风险接受：容器仅绑定回环、以非 root 与 0400 合成本地凭据运行，且不持有生产数据，因此 bookworm userland 暴露被接受用于本地开发。每当 tag 或 digest 变更时，按下方回滚与依赖变更规则重新生成解析与扫描验收证据。

## 所有权

- **公共命令与事件所有者**: 仓库工作流维护者。
- **Compose 与依赖清单所有者**: 基础设施维护者。
- **API/Billing 就绪检查所有者**: 各服务所有者；实现与无密钥 Prometheus 探针指标保持独立。
- **PostgreSQL 本地数据所有者**: 由项目哈希标识的开发者/工作区。
- **安全评审**: 镜像、digest、许可证、绑定、密钥传输或远程 context 变更时必需。

## 已考虑的备选方案

### 无 root/原生主机服务

已拒绝。包管理器与服务管理器在受支持平台间不同，版本更难隔离，且工作流将需要 SF02 明确禁止的系统安装/升级权限。

### 无 Compose 的 Docker SDK 编排

已拒绝。它将重造 Compose 的声明式网络、卷、健康、状态协调与 down 行为，同时增加 SDK 依赖与更大的 API 兼容面。

### 仅 Makefile 或 shell 的 Compose 包装

已拒绝。跨进程锁、严格 URL 解析、JSON 状态翻译、脱敏与确定性负向测试更适合维护中的 Python 工作流工具，否则将被重复实现。

### 每平台/工作区独立 Compose 定义

已拒绝。多平台 index 镜像、命名卷与发布端口已提供公共定义；override 将引入分歧契约。

## 失败模式与控制

| 失败模式 | 要求行为 | 恢复 |
|--------------|-------------------|----------|
| Docker/Compose 缺失、daemon 不可用、远程端点、不受支持平台 | 在依赖配置的资源变更前以稳定工具/运行时诊断失败 | 启动或安装已评审本地运行时；重跑同一命令 |
| 镜像缺失 | 仅拉取已提交 digest 并单独报告拉取 | 修复 registry/网络/磁盘；重跑且不删除资源 |
| Digest/平台不匹配 | 在创建容器前失败 | 在依赖变更 PR 中评审并替换清单 digest |
| 端口被其他进程/项目占用 | 在项目创建前失败；永不带凭据探测或停止占用者 | 释放端口或修改对应 URL，然后重跑 |
| 依赖存活但认证/查询失败 | 在共享截止时间内返回 dependency-not-ready，保留可检查资源，脱敏原始输出 | 修复合成本地凭据/配置；重跑 |
| 并发 up/down | 一个持有者继续；失败者立即失败且无副作用 | 活动操作结束后重试 |
| 12 位十六进制项目碰撞/全指纹不匹配 | 在变更前失败并报告所有权冲突 | 使用文档中的显式恢复；永不接管另一工作区 |
| 进程/主机中断 | 内核释放锁；项目资源与卷仍可状态协调 | 重跑 `make dev` 或 `make dev-down` |
| down 期间 `.env.local` 缺失/损坏 | 在无密钥情况下计算项目 id/指纹，并用安全子进程环境占位解析 Compose | 重跑 down；仅当 Compose 解析失败时使用精确项目/指纹回退 |
| stop 超过服务优雅期或 75 秒外层边界，或需要强制 kill | 报告失败；永不删除卷 | 检查安全日志/状态，修复运行时，重试 down |
| 精确拥有的容器上存在任一非当前镜像 | 校验期望 index/child digest，替换容器，保留其声明的命名卷 | 重试或回滚期望依赖集；仅镜像不匹配本身不是所有权冲突 |
| 工作区已移动 | 创建新身份；旧标签资源被报告但不被接管 | 回到旧路径或遵循显式已评审恢复流程 |

## 安全与数据后果

- 本地凭据使用确定性合成语法，留在被忽略的 `.env.local` 与短生命周期 Compose 子映射中，仅成为 0400 UID/GID 拥有的容器密钥文件，且从不适于生产。
- `127.0.0.1` 发布与项目网络降低暴露，但不使环境适于不受信任网络。
- PostgreSQL 是唯一持久化本地事实源。普通生命周期操作永不运行迁移、seed 数据、变更角色或删除卷。
- 即使命名卷由普通 down 保留，Redis 内容仍可重建。
- Grafana `/var/lib/grafana` 为 tmpfs，在 SF02 中不创建匿名卷；若 SF19 引入持久仪表盘、数据源或密码轮换语义，必须记录新决策。

## 上线

1. 将本 ADR 接受为授权实现的设计决策，然后合入 Root Make/event v2 契约、迁移通知、清单 schema 与失败测试，同时 v1 `SF02_NOT_READY` 仍活动，且实现验证保持 Pending。
2. 解析并扫描官方多平台 digest；提交运行时清单与 Compose 资产。
3. 实现受保护的工作流激活候选，并将全部已枚举事件消费者迁移到 v2 标准封装，尚不替换公共 SF01 过渡。
4. 在共享健康契约更新后，添加 API/Billing PostgreSQL 就绪检查与安全探针指标。
5. 运行可访问性与脏工作区门禁，以及隔离的 Linux x86_64 与代表性 macOS arm64 生命周期/安全/持久化/恢复/性能验收证据。
6. 仅在全部验收证据通过后，原子替换 SF01 的 dev/dev-down 过渡、事件输出、帮助与恢复文档，然后将 Implementation Verification 标为 Verified，且不改变已 Accepted 的设计状态。

## 回滚

- 在经评审 PR 中一并回退工作流适配器、Compose 资产、清单、event v2 激活/健康更新与服务就绪检查变更；恢复 v1 运行时输出，同时保留不可变的 v2 迁移历史。
- 若无法建立生命周期安全，恢复 SF01 失败关闭的 `SF02_NOT_READY` 适配器；不模拟成功。
- 永不使用回滚删除项目卷。既有项目作用域 PostgreSQL/Redis 卷保留，供后续兼容前向修复或显式手工恢复。
- 镜像回滚同时变更 tag、OCI index digest 与两个 child digest，并重新校验两个目标平台 manifest 与扫描验收证据。

## 后果

### 正面

- 一套公共工作流与一份 Compose 定义覆盖两个受支持平台与多个 worktree。
- 不可变镜像、认证探针、有界等待、锁与项目作用域使重复生命周期操作可诊断、可恢复。
- 独立工作流锁仅为 PostgreSQL 主机查询增加一个已评审的 asyncpg 0.30.x 依赖；不引入 Docker SDK 或第二套编排 CLI。

### 负面

- Docker/Compose 版本与本地 daemon 可用性成为硬前置条件。
- Compose environment-source 密钥支持与固定镜像运行时 UID/GID 是硬兼容要求，需要显式跨平台测试。
- Grafana 本地状态在普通 down/up 间有意重置；持久监控配置等待 SF19。
- 移动工作区按设计不会自动接管旧卷。

## 需求到验收证据的追踪关系（T073）

| 区域 | 主要验收证据 / 任务 |
|------|--------------------------|
| 公共入口 + 激活门禁 (FR-001) | `tools/workflow/cli.py` `SF02_NOT_READY`；激活 T074，在 T068–T073 之后 |
| 不可变 digest / 三依赖 (FR-002–003) | `ops/workflow/local-dependencies.json`；compose/清单测试 |
| 配置 / 回环 / 密钥 (FR-004–009) | `local_env/config.py`；配置/安全测试 |
| 启动就绪检查 60s / 重复 15s (FR-013–014, SC-001–002) | 生命周期 + 性能测试框架；平台验收证据 T069–T070 |
| 所有权 / 隔离 / 锁 (FR-016, FR-023) | `local_env/identity.py`；身份/并发测试 |
| 非破坏性 down + 卷 (FR-017–021) | `lifecycle.stop_*` / compose down；持久化测试 T076 |
| Event v2 + 消费者迁移 (FR-026) | `events.py`；contracts/events/sf02_transition 测试 |
| 仅 API/Billing 就绪检查 (FR-025) | 服务 `database.py`/`health.py`；服务测试 |
| 安全脱敏 (Constitution II) | security/secret_scan 测试；运行手册 |
| 双平台 + 易用性 (SC-001, SC-008) | `specs/002-local-dependency-lifecycle/evidence/` 下的 T069–T071 验收证据文件 |

## 依赖 / 安全 / schema 影响

- **新增/变更产物**: Compose `infra/docker/compose.local.yml`；生命周期包 `tools/workflow/local_env/`；workflow event v2 schema；health OpenAPI **1.1.0**（仅 API/Billing 的向后兼容 503 形状）；仅独立工作流锁中的 workflow `asyncpg` 0.30.x。
- **无**业务 schema/Alembic/seed；**无** Gateway/Admin 依赖探针；**无** Kafka 于 SF02 依赖集。
- 每当 tag 变更时重新评审 digest 与扫描（见上文已解析依赖验收证据）。

## 激活 / 弃用通知

- **当前运行时（post-T074）**: 公共 `make dev` / `make dev-down` 运行真实 SF02 生命周期；公共 `emit_event` / 聚合路径发出 event v2 标准封装。`make start` / `make stop` 将同一中间件生命周期与主机应用进程组合。
- **共享分发**: `execute_dev_guarded` / `execute_dev_down_guarded` 仍是公共目标与测试使用的可注入接缝。
- **激活（T074, 2026-07-25）**: 在 Linux amd64 + macOS arm64 验收证据、完整质量门禁、负责人授权的易用性验证协议（T071）以及本 ADR 验证翻转之后：移除公共中间件入口的运行时 `SF02_NOT_READY`，将 event v2 封装设为默认，发布匹配的帮助/恢复文本，将 **Implementation Verification: Verified**。
- **弃用**: v1 Make/event 产物与 `emit_event_v1` 在下一 tagged 发布前保持不可变；消费者使用 v2 读取器。

## 保留卷的回滚决策点

回滚一并回退适配器/Compose/清单/v2 激活/服务就绪检查，并在需要时恢复 `SF02_NOT_READY`。**项目 PostgreSQL/Redis 命名卷永不因回滚或普通 down 删除。** 镜像回滚将 tag + index + 两个 child digest + 扫描验收证据作为一体变更。

## 验收证据索引

- `specs/002-local-dependency-lifecycle/evidence/README.md`

## 参考

- `specs/002-local-dependency-lifecycle/spec.md`
- `specs/002-local-dependency-lifecycle/research.md`
- `specs/002-local-dependency-lifecycle/quickstart.md`
- `specs/002-local-dependency-lifecycle/tasks.md`
- `ops/runbooks/local-environment.md`
- `shared/contracts/repository-workflow/v2/`
- `shared/contracts/local-environment/v1/`
- `specs/001-repository-workflow-baseline/contracts/make-workflow.md`
- `specs/001-repository-workflow-baseline/contracts/workflow-event.schema.json`
- `specs/001-repository-workflow-baseline/contracts/environment-mode.md`
- `.specify/memory/constitution.md`
