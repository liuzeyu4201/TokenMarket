# Phase 0 Research：火山方舟凭证与额度验证

**Feature**: `006-volcano-key-validation`  
**Date**: 2026-08-01  
**Status**: Complete — Technical Context 中的未知项均已决议

## Decision 1：能力归属 proxy-gateway，无新微服务

**Decision**: SF06 由 `services/proxy-gateway/` 拥有：领域端口
`CredentialValidator`、火山方舟基础设施适配器、并发闸门、脱敏与分类、
以及面向内部调用方的版本化结果契约。不新建服务；不把适配器放入
Python API Service；Billing / Admin / Frontend 本功能无变更。

**Rationale**: 宪章 I 与 `2-Go代理网关开发规范.md` 将平台适配器放在网关；
SF16 健康探活将在网关热路径附近运行；SF01 已提供 Go 工程基线。
SF08（API Service）通过内部 HTTP 消费本能力，避免 Python 复制一份上游协议解析。

**Alternatives considered**:

- 仅在 API Service 用 Python 实现验证：与网关适配器双源漂移，健康检查仍要在 Go 侧重做。
- 独立 validation-service：V0.1 流量与职责不足以承担新服务/ADR 成本。
- 共享 polyglot 库：无既有基础设施，过早。

## Decision 2：认证与模型列表使用数据面 `GET /api/v3/models`

**Decision**: 使用火山方舟数据面 Base URL（默认
`https://ark.cn-beijing.volces.com/api/v3`，可配置）与
`Authorization: Bearer <api_key>` 调用：

```http
GET {base_url}/models
```

- HTTP 200 + 可解析的模型列表 → 认证有效；从 `data[].id`（或契约固定字段）提取模型标识。
- 401 / 鉴权类 → `invalid`
- 403 / 权限类 → `forbidden`
- 429 → `rate_limited`（见 Decision 6）
- 超时 / 连接失败 → `timeout` 或 `temporary_unavailable`
- 5xx → `temporary_unavailable`
- 200 但 body 无法按契约解析 → `invalid_response`

社区与工程规范草稿一致使用该路径作为 Key 探活；实现时用契约测试固定响应 JSON
形状，字段名以当期官方文档复核结果写入 `contracts/upstream-volcano-models.md`。

**Rationale**: 单次读请求即可同时验证鉴权与模型可见性，符合 3 秒截止与幂等读重试。

**Alternatives considered**:

- 用 `POST /chat/completions` 探活：可能产生计费/副作用，超时风险更高。
- 仅 HealthCheck 空调用：无法得到模型列表以满足 FR-002a。

## Decision 3：无 Key 作用域官方额度 API → 强制 `quota_unavailable`（默认路径）

**Decision**: 截至本计划研究日，**未找到**可用卖家 API Key（Bearer 数据面）直接查询
「该 Key / 该账号剩余额度」的稳定公开数据面接口。账户余额与充值位于控制台/账单/
管控面（IAM 签名），**不能**用卖家提交的方舟 API Key 可靠读取。

因此 V0.1 默认验证流水线在认证成功后：

1. **不得**调用不存在的占位 `GetBalance` 并返回 0；
2. **必须**将额度步骤判定为 `error_category=quota_unavailable`，
   `remaining_quota` / `quota_unit` **为空（omit/null）**，不得为 0；
3. **不得**归类为 `zero_quota` 或 `success`。

若后续官方文档出现 **可用同一 API Key 鉴权** 的可信额度读路径，则通过契约版本
升级（`volcano-key-validation` v1 → v1.1 或 v2）启用真实额度映射；启用前须：

- 在 `research` 附录或 ADR 记录端点、字段、单位与错误映射；
- 契约测试金标覆盖正余额、零余额、字段缺失；
- 仅当官方明确剩余为 0 时才产出 `zero_quota`。

**Rationale**: 直接落实澄清 Q1 与 FR-013/SC-003；否决工程草图「无余额则返回零值」。

**Alternatives considered**:

- 返回零额度以便 SF08 拒绝接入：语义错误，把「查不到」当成「没钱」。
- 用 IAM 管控面查账户余额：需要平台持有卖家火山账号 AK/SK，超出 SF06 输入模型与信任边界。
- 最小 chat 探活间接推断：可能计费、不稳定，且仍非额度读。

**对 SF08 的影响（调用方）**: 在官方额度 API 就绪前，SF08 的
「`remaining_quota > 0` 才接入」门禁 **无法** 被 SF06 满足为 `success`。
SF08 须在其规格/计划中显式处理 `quota_unavailable`（拒绝接入并提示、或产品改门禁）。
本功能不放宽为 `success`。

## Decision 4：错误分类表与 HTTP 映射（稳定枚举）

**Decision**: 对外只暴露规格枚举；上游 status / error code 仅作内部映射输入。

| 上游信号（摘要） | `error_category` | `validity` | `availability` | 可重试 |
|------------------|------------------|------------|----------------|--------|
| 200 + 模型可解析 + 额度可信且 >0 + 有 V0.1 模型 | `success` | valid | available | — |
| 200 + 额度可信且 =0 | `zero_quota` | valid | unavailable | 否（补额度后） |
| 200 + 无可信额度源/字段 | `quota_unavailable` | valid* | unavailable | 视产品 | 
| 200 + 额度 OK 但 V0.1 模型交集空 | `no_supported_models` | valid | unavailable | 否（换模型权限） |
| 401 / 鉴权失败 | `invalid` | invalid | unavailable | 否 |
| 403 / 权限不足 | `forbidden` | invalid | unavailable | 否 |
| 429 限流（RPM/TPM 等） | `rate_limited` | valid* | unavailable | 是 |
| 超时 | `timeout` | unknown/prior | unavailable | 是 |
| 网络错误 / 5xx | `temporary_unavailable` | unknown/prior | unavailable | 是 |
| Body 非法 / 契约不符 | `invalid_response` | unknown | unavailable | 否（告警） |
| platform ≠ volcano | `unsupported_platform` | — | unavailable | 否 |
| 并发闸门拒绝 | `temporary_unavailable` | — | unavailable | 是 |

\* `validity`：当次能确认认证通过则为 `valid`；超时/5xx 不得声称 `invalid`。  
永久类仅 `invalid` / `forbidden` 可供调用方将持久认证事实标为无效（FR-007a）。

官方错误体中的 `QuotaExceeded` 等字符串 **不得** 直接当 `zero_quota`，除非契约明确
「剩余额度=0」语义；免费试用耗尽等若无法映射为精确剩余，归 `quota_unavailable`
或独立映射表评审后扩展（默认保守：非明确零则不用 `zero_quota`）。

**Rationale**: FR-005/010/011；防止文案耦合。

## Decision 5：V0.1 支持模型集合为配置化 allowlist 交集

**Decision**: `supported_models = intersect(upstream_model_ids, v01_chat_allowlist)`。  
Allowlist 来自配置（环境变量或已提交默认列表），仅包含 V0.1 Chat Completions
所需模型 ID（或官方文档中的 endpoint/model 标识）。交集为空 →
`no_supported_models`（澄清 Q2）。  
默认种子列表在实现时写入 `contracts/v01-chat-models.md` 并可由配置覆盖；测试锁定
交集逻辑而非某一官方全集。

**Rationale**: FR-002a；产品模型集可变，配置优于硬编码唯一厂商列表。

## Decision 6：`retry_after_seconds` 与钳制

**Decision**:

- `rate_limited` **必须**带 `retry_after_seconds`（正整数秒）。
- 优先解析上游 `Retry-After`（秒或 HTTP-date → 秒）或官方 JSON 中的明确重试字段。
- 缺失时默认 **5**（可配置 `VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS`）。
- 上限钳制 **300** 秒（可配置，默认 300）：`min(parsed_or_default, max_clamp)`，
  且结果 ≥ 1。

**Rationale**: 澄清 Q5；防止异常大值拖垮调度。

## Decision 7：超时、取消与有界重试

**Decision**:

- 单次验证总预算 **3s**（`context` deadline）；调用方更短 deadline 取更严者。
- 出站 HTTP client 单次请求超时 ≤ 剩余预算；取消立即传播到 `http.Request`。
- 仅对 **幂等 GET** 且分类为瞬时网络错误（连接重置、暂时性 DNS 等，非 4xx）
  做有界重试：最多 **1** 次重试，总耗时仍 ≤ 3s；4xx/已解析分类不重试。
- 不重试 429（直接 `rate_limited`）。

**Rationale**: ER-005；避免放大上游压力。

## Decision 8：并发闸门（进程内）

**Decision**: 进程内信号量：

- 全局：默认 32（`VOLCANO_VALIDATE_GLOBAL_CONCURRENCY`）
- 单凭证：默认 1（`VOLCANO_VALIDATE_PER_CREDENTIAL_CONCURRENCY`）  
  单凭证键 = 对原始 Key 的 **不可逆短哈希**（HMAC 或 salted hash，密钥来自进程配置，
  **不**等于 SF08 去重指纹；仅用于闸门分桶，不落盘、不回传完整键）。

超限 → 不发起上游调用，返回 `temporary_unavailable`（可重试），可带
`retry_after_seconds=1`（或默认 5，实现选小值并测）。

**Rationale**: 澄清 Q4 / FR-012a；无 Redis 依赖（验证无状态）。

## Decision 9：内部调用面 = Go 端口 + 内部 HTTP（含宪章 II 部署约束）

**Decision**:

1. **领域端口**（网关内）：`Validate(ctx, CredentialValidationRequest) (CredentialValidationResult, error)`  
   供 SF16 / 同进程用例直接调用。
2. **内部 HTTP**（网关）：`POST /internal/v1/provider-credentials/validate`  
   契约见 `contracts/`；仅当 `PROVIDER_VALIDATE_INTERNAL_ENABLED=true` 且校验
   `X-Internal-Token`（或等价共享秘密）时挂载。  
   供 SF08（API Service）跨进程调用。
3. **不**提供面向卖家的公开验证 UI/API。
4. **部署与认证强度（C1 / 宪章 II）**：
   - 默认 **disabled**（`PROVIDER_VALIDATE_INTERNAL_ENABLED=false`）。
   - **local/dev**：允许回环监听 + 共享 token（隔离开发网）。
   - **test/prod 或任何非隔离网络**：共享静态 token **不得**作为唯一防护。
     启用时 MUST 同时满足：
     - 监听/入口仅限 loopback 或私网 CIDR / 服务网格内地址，**禁止**将内部路由
       挂在对公网开放的监听器上；且
     - 优先使用 mTLS 或平台服务身份；若暂无 mTLS，则 MUST 保持路由禁用，
       或仅通过已互信私网 + 网络策略到达，并在 runbook 记录风险接受到期日。
   - 启动校验：当 `APP_ENV` ∈ {`test`,`prod`}（或等价非 local）且内部路由启用时，
     若未配置「私网/回环绑定」或显式 `PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK=true`
     （仅私网运维、默认 false），**fail-closed 拒绝启动**。
   - 负向测试：enabled + 模拟「非回环/非私网暴露意图」→ 启动失败或拒绝挂载。

**Rationale**: 内部调用 + 跨服务消费；密钥不经公开面；满足「公网前强于静态共享令牌」的宪章要求。

## Decision 10：安全与遥测

**Decision**:

- 原始 Key 仅存在于请求处理栈与出站 Header 构造；返回后尽快使引用不可达；
  测试用合成 Key。
- 日志/指标/错误：平台、`error_category`、耗时、上游 status 类、`request_id`；
  凭证仅 `credential_ref`（不可逆短哈希前缀），禁止 Authorization 头与 Key 正文。
- 指标低基数：`platform`、`error_category`、`result`（ok/fail）、`le` 桶。
- 契约/fixture JSON 禁止真实 Key。

**Rationale**: 宪章 II、FR-009、ER-002/006。

## Decision 11：无持久化、无迁移

**Decision**: SF06 不引入 PostgreSQL/Redis 表；不写 Key 生命周期。  
状态合并规则文档化供 SF08/SF16（FR-007a），本功能单测只断言单次结果分类。

**Rationale**: 澄清 Q3；FR-007/008。

## Decision 12：测试策略

**Decision**:

| 层 | 内容 |
|----|------|
| 单元 | 分类器表驱动；脱敏；allowlist 交集；retry_after 默认/钳制；闸门超限 |
| 契约 | 金标上游 JSON（models 成功/空/畸形）；错误 status→category |
| 集成 | `httptest.Server` 模拟火山；真实超时/取消；并发 33 与同 Key 第 2 路 |
| 负向 | 日志扫描无 Key；取消后无泄漏断言（在可控替身下） |
| 覆盖率 | 适配器与 domain 包 ≥80% 行；分类与脱敏分支直接覆盖 |

不在 CI 默认路径调用真实火山；可选 `VOLCANO_LIVE_SMOKE=1` 本地人工。

## 官方文档复核清单（实现前必做）

实现任务须打开当期文档并更新 `contracts/upstream-volcano-models.md`：

1. Base URL 与区域（北京/上海等）  
2. `GET /api/v3/models` 请求/响应字段  
3. 错误码表与 401/403/429 语义  
4. 是否新增 **API Key 可调用** 的额度接口；若有则启动额度映射变更流程  

研究日结论：**默认无额度接口 → `quota_unavailable`**。

## 已解决的 NEEDS CLARIFICATION 映射

| 原未知项 | 决议 |
|----------|------|
| 额度 API 是否存在 | 默认不存在 → `quota_unavailable`（D3） |
| 验证归属服务 | proxy-gateway（D1） |
| 上游探活路径 | GET models（D2） |
| 重试与钳制 | 默认 5s，上限 300s（D6） |
| 并发实现 | 进程内 32/1（D8） |
| 跨服务调用 | 内部 HTTP + token（D9） |
| 模型 allowlist | 配置交集（D5） |
