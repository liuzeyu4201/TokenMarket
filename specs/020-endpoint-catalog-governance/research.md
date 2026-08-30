# Phase 0 Research：V0.2 契约与端点目录治理

**Feature**: `020-endpoint-catalog-governance`
**Date**: 2026-08-31
**Status**: Complete — Technical Context 中无未决议 NEEDS CLARIFICATION

## Decision 1：共享契约为唯一事实源，判定逻辑只在 gateway 领域包

**Decision**: 机器目录与领域契约提交于 `shared/contracts/`（本功能 `contracts/`
为评审源并字节物化）。`Admit`/`Load` 的权威实现位于
`services/proxy-gateway/internal/domain/endpcatalog`。api/billing/admin 只校验
`catalog_major` 与 schema 完整性，不复制匹配算法。仓库级 pytest 消费同一
`catalog.json`。

**Rationale**: 宪章 I 要求契约先于消费者；网关是数据面入口，必须用同一快照判定。
三套 Python 重写匹配会造成 SF18 漂移。

**Alternatives considered**:

- 各服务复制完整判定：实现快，语义必然分叉。
- 独立 catalog-service：V0.2 批次 A 不需要新服务/新网络依赖，违反最小设计。
- 把目录嵌入 Go `embed` 而不放 shared/contracts：Python 测试与文档无法同源。

## Decision 2：JSON 目录 + 领域校验器，不引入 jsonschema 运行时库

**Decision**: `catalog.json` 用 JSON Schema 2020-12 文档约束结构；Go/Python 用显式
校验器强制 FR 完整性（稳定性、状态性、传输、计量、夹具、唯一键、官方来源）。
不新增第三方 schema 库，避免锁文件扩大。

**Rationale**: 仓库现有契约测试手写结构断言；领域规则（最长模板匹配、Project
模式）不是纯 JSON Schema。显式校验器可单测每个拒绝分支。

**Alternatives considered**:

- 引入 `jsonschema` / `santhosh-tekuri/jsonschema`：可用但本 SF 规则超出 schema。
- YAML 源：人类友好但排序与注释会造成非确定性；JSON + 生成 Markdown 更稳定。

## Decision 3：冻结日枚举来自官方公开数据面，含糊者不进 stable

**Decision**: `freeze_date=2026-08-31`。覆盖基线点名的家族：

| 厂商 | 进入 stable 的数据面家族 | 默认 control_plane | 至少一条 preview/beta |
|------|--------------------------|--------------------|------------------------|
| OpenAI | Responses、Chat Completions、Models、Embeddings、Moderations、Images、Audio、Files、Uploads、Batches、Fine-tuning、Vector Stores、Realtime、Conversations | organization/admin/usage/billing/API keys/projects/users | 明确 alpha/beta（如 graders alpha） |
| Anthropic | Messages、count_tokens、Message Batches、Models | Admin/组织/API keys/workspaces/invites/cost | Files 或其他官方 beta |
| Vertex | Publisher Model `generateContent`/`streamGenerateContent`/`countTokens`/`computeTokens`/`embedContent`/`predict`/`rawPredict`/`streamRawPredict`/`serverStreamingPredict`/`predictLongRunning`/`fetchPredictOperation`、cachedContents、batchPredictionJobs、tuningJobs | IAM、项目计费、自定义 Endpoint 管理 | v1beta1 仅当评审为非稳定 |

Assistants/Threads：基线未点名为 V0.2 承诺；若官方仍公开则登记为 `stable` 并标注
`owning_sf=SF19` 以免出现“公开稳定却未枚举”；若已弃用则登记 `preview` 并默认拒绝。
本实现将仍公开的 Assistants/Threads 记为 `stable`（数据面资源），不承诺优先实现。

Volcano 不进入本目录。

**Rationale**: SF01 验收要求 100% 唯一记录，不是“抽样”。含糊接口按基线不进
stable。Vertex 稳定性不由 URL 是否含 `beta` 推断。

**Alternatives considered**:

- 只登记 Chat Completions/Messages/generateContent：无法满足“全兼容可枚举”。
- 运行时抓取厂商 OpenAPI：禁止自动上线新 API，且不确定。

## Decision 4：控制面显式登记，避免与未登记混淆

**Decision**: 账号/组织/IAM/支付/上游凭据管理路径写入目录且 `stability=control_plane`。
匹配成功 → `CONTROL_PLANE_NOT_ALLOWED`。完全无记录 → `ENDPOINT_NOT_CATALOGED`。
使用规范化 path 模板与最长前缀/模板匹配，禁止双匹配成功。

**Rationale**: 基线要求两种错误码可区分，便于审计“已知禁止”与“未知拒绝”。

**Alternatives considered**:

- 仅前缀黑名单不入库：无法证明评审过，也难以生成人类清单。

## Decision 5：领域契约先行，实现延后

**Decision**: 本 SF 发布 Project/Connection/route/usage/pricing/ledger/audit 的
OpenAPI 或事件 schema 与兼容策略。字段足够表达后续不变量（模式不可变、凭据
write-only、金额整数、账本追加、未决不得记 0）。HTTP 处理与表结构属于 SF10+。

**Rationale**: 宪章 contract-first；SF 来源明确“维护契约”而非实现买卖流程。

**Alternatives considered**:

- 本 SF 同时做 Project CRUD：跨越硬依赖（SF09）且混入无关 SF。

## Decision 6：人类清单由 catalog.json 确定性生成

**Decision**: 生成器按 `provider, path_template, method` 排序，固定换行，不写时钟。
`CATALOG.md` 提交入库；测试比较二次生成字节。源文件 `catalog.json` 使用稳定
键顺序（Python `json.dumps(..., indent=2, sort_keys=True)` 或等价 Go
编码策略由测试锁定）。

**Rationale**: 验收“工作树无非确定性差异”。

## Decision 7：不把 new-api 放入核心契约

**Decision**: 无 new-api 适配器、无统一请求格式 schema、无其用户/渠道/额度模型。
厂商覆盖线索只用于反查官方文档。

**Rationale**: `new-api取舍与自研复杂度评估.md` 与总纲排除项。

## Decision 8：ADR 005 记录共享目录抽象

**Decision**: 新增 `docs/decisions/005-endpoint-catalog-governance.md`，满足宪章
“新共享抽象必须有 ADR”。
