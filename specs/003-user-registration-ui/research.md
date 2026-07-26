# 研究：用户注册与初始界面

**特性**: `003-user-registration-ui`
**日期**: 2026-07-23
**状态**: 完成 — 无未解决的 `NEEDS CLARIFICATION`

## 决策 1: 账户域归属 API Service

**决策**: 用户注册用例、`users` 表与注册幂等表由 **API Service** 单独拥有。Billing/Admin/Gateway 不读写用户表。前端在本地开发中直接调用 API Service 的版本化业务路径；Gateway 仍只负责 AI 代理流量，本功能不扩展 Gateway 业务注册路由。

**理由**: 宪章要求域规则与持久化同属一个服务；SF01 已将 API Service 定为应用域服务并具备 PostgreSQL readiness。注册不涉及代理计量。

**备选方案**:

- 新建独立 identity-service：过早拆分，增加部署与事务边界，V0.1 无第二消费者。
- 经 Gateway 转发注册：Gateway 职责被扩大，偏离“仅代理 AI 流量”边界。

## 决策 2: 统一业务响应包络 + OpenAPI 契约先行

**决策**: 所有注册相关 HTTP 响应使用版本化包络：

```json
{
  "code": "0",
  "message": "success",
  "data": {},
  "request_id": "uuid",
  "timestamp": "ISO-8601 UTC"
}
```

契约以 OpenAPI 3.1 形式置于本特性 `contracts/`，实施时同步到 `shared/contracts/user-registration/v1/` 与 `docs/api` 索引。业务结果以 `code` 区分；HTTP 状态做粗粒度映射（4xx/429/5xx）。成功 `code` 为字符串 `"0"`（与工程规范示例一致）。

**理由**: 产品全局规范与 SF03 要求统一包络；机读契约满足宪章 contract-first 与前端类型对齐。

**备选方案**:

- 仅用 HTTP 状态、无业务码：难以区分占用 / 软删 / 幂等冲突 / 限流。
- gRPC：仓库 HTTP/OpenAPI 基线已定，V0.1 无需求。

## 决策 3: 手机号规范化规则（大陆 11 位 + 噪声清洗）

**决策**: 单一纯函数 `normalize_cn_mobile(raw) -> Result[str, ValidationError]`：

1. Unicode NFKC，全角数字 → 半角。
2. 去除全部空白字符（含中间空格）。
3. 若以 `+86` 或 `86` 开头且后续长度合理，去掉此前缀（仅当剩余为 11 位候选时）。
4. 结果必须匹配 `^1[3-9]\d{9}$`，否则字段错误。
5. 持久化与唯一性、限流手机号维度 **只使用** 规范化后的 11 位串。

**理由**: 澄清会话锁定范围；可单测矩阵覆盖噪声变体与非大陆号。

**备选方案**:

- 严格只收连续 11 位：用户体验差，空格/`+86` 常见。
- 完整 libphonenumber 多国：范围过大，增加假阳性与依赖。

## 决策 4: 角色枚举包含 `both`，不含密码/邮箱

**决策**: V0.1 用户角色为 PostgreSQL ENUM `buyer | seller | both`。不建 `password_hash`、不强制 `email`。状态 ENUM 至少含 `active`（新建默认）；可预留 `suspended` 但不在本功能流转。`admin` 角色不在本功能创建路径出现。

**理由**: 对齐 SF03 与澄清后的规格；周度 Spec 中的明文密码被宪章禁止，且本功能明确不签发会话。

**备选方案**:

- 工程范例中的 `buyer|seller|admin` + email/password：与 SF03/安全宪章冲突。
- 角色互斥仅 buyer/seller：产品已允许 `both`，自买自卖隔离留给 SF05。

## 决策 5: 幂等事实存 PostgreSQL，24h 窗口

**决策**: 表 `registration_idempotency_records` 为幂等权威源（非 Redis 唯一存储）：

- 唯一键：`idempotency_key`（客户端 UUID 或 64 字符内可打印串）。
- `request_hash`：对规范化后请求体字段的稳定摘要（phone_normalized + nickname + role），不含原始手机号明文变体差异。
- `user_id`、业务结果快照（成功时的 `data` 子集，已脱敏）、`created_at`、`expires_at = created_at + 24h`。
- 窗口内：同键同摘要 → 重放首次成功包络；同键异摘要 → 冲突。
- 窗口外：键失效，返回可机读过期错误；不返回首次成功 `data`；账户唯一性仍兜底。

写入：用户行与幂等行在 **同一短事务** 中提交；仅提交成功后对外成功。

**理由**: 宪章规定 Redis 不得作为耐久事实唯一副本；注册结果必须可在 DB 恢复后重放。24h 来自澄清。

**备选方案**:

- 仅 Redis TTL 24h：进程/刷库后丢失重放能力，违反 ER-003。
- Redis 缓存 + PG 权威：可作后续优化，V0.1 不必要。

## 决策 6: 限流用 Redis 固定窗口，失败关闭可降级策略

**决策**:

- 维度键：`reg:rl:ip:{ip}`、`reg:rl:phone:{phone_normalized}`。
- **计数规则（防枚举）**：IP 桶对每次注册尝试计数（含校验失败）；phone 桶 **仅** 在规范化成功后按 11 位号计数。超限一律 `RATE_LIMITED` + HTTP 429，响应形状/文案 **不** 随占用、软删、未知号变化。
- 窗口 15 分钟；默认上限 IP=20、phone=5；INCR + EXPIRE 首次设置。
- 尝试在 **进入写路径前** 应用限流；超限不写账户。
- 客户端 IP：优先 `X-Forwarded-For` 最左可信跳（本地直连则用 socket peer）；文档标明生产须由受信入口设置。
- **Redis 不可用**：返回 503 可重试服务错误并 **拒绝写入**（fail closed），避免无限刷库；指标记录 `rate_limit_backend_unavailable`。

**理由**: 宪章允许 Redis 作 rate-limit 存储；双维度满足 FR-018/019。Fail-closed 优先防滥用。

**备选方案**:

- 仅 PostgreSQL 计数表：可行但增加写放大；V0.1 Redis 已在 SF02 依赖集。
- Redis 不可用时放行：实现简单但违背安全默认。
- 限流放 Gateway：本功能不经 Gateway，且域名额属 API。

## 决策 7: 软删除手机号专用业务码

**决策**: `phone_normalized` 在 **全表**（含 `is_deleted = true`）唯一。查到已删账户 → `code=ACCOUNT_UNAVAILABLE`，**HTTP 409**（与 `contracts/business-codes.md` 一致，不用 422），文案中性“账户不可用，请通过恢复流程处理”，不泄露昵称/角色。活跃占用 → `PHONE_ALREADY_REGISTERED`。两者前端可区分。

**理由**: 澄清选项 B；全表唯一防止静默重建。

**备选方案**:

- 与占用相同中性冲突：澄清已否决。
- 允许软删号重建：破坏审计与恢复策略。

## 决策 8: 前端最小壳层技术选型

**决策**:

- 在现有 Vite + React 18 + TS strict 脚手架上增加 **React Router**（声明式路由）。
- 路由：`/` 首页占位、`/register` 注册、`*` 未找到/未开放。
- 布局：顶栏导航含「首页」「注册」；无设计系统、不强制 Tailwind（可用少量全局 CSS 满足对比度与表单布局）。
- API 客户端：`fetch` 封装 + 与 OpenAPI 对齐的手写类型（或后续从契约生成）；请求头 `X-Request-ID`、`Idempotency-Key`；**单次超时 10s**；注册 POST **禁止自动重试**；用户手动重试复用同一幂等键。
- 状态：注册表单本地 React state 即可；不引入全局 auth store（无登录）。
- 测试：Vitest + Testing Library 覆盖路由可达、表单校验展示、成功/错误映射、超时与无自动重试。

**理由**: 规格要求最小可导航壳层 + 注册页；与前端规范目录演进兼容且依赖增量最小。

**备选方案**:

- 一次引入完整 Tailwind/Zustand/React Query：超出“开始搭建 UI”范围。
- 无路由、条件渲染：难验收三类路由与深链注册。

## 决策 9: 迁移与回退

**决策**: Alembic 修订 `0002_users_registration`（名称以实施为准）在 `api-service`：

- 创建 ENUM、`users`、`registration_idempotency_records` 及唯一/检查约束。
- `upgrade`/`downgrade` 对称；禁止编辑已应用修订。
- 回退：先停写注册流量 → `alembic downgrade` → 保留备份策略说明；不在应用启动时自动 migrate。

**理由**: 宪章迁移纪律；API Service 已有 baseline 与迁移入口。

## 决策 10: 可观测性指标、告警与脱敏

**决策**:

- 指标（无高基数标签）：`registration_attempts_total{result=...}`、`registration_duration_seconds`、`registration_rate_limited_total`、`registration_phone_conflicts_total`、`rate_limit_backend_unavailable`（或等价）。
- 日志：`request_id`、结果码、耗时、`user_id`（成功时）；手机号仅脱敏形式（如 `*******1234`）或完全不出现。
- 响应 `data` 不回显完整手机号；可选 `phone_masked`。
- **告警（本特性必做）**：提交 Prometheus 规则覆盖 (1) 注册 5xx/`SERVICE_UNAVAILABLE` 升高 (2) 限流后端不可用 (3) 异常失败率；severity 与 owner=API Service 写在 `ops/runbooks/registration.md`（或等价路径）；规则文件放 `ops/alerts/`（或仓库标准告警目录）。本地开发不强制实时 pager，但规则与 runbook 必须作为交付物合并。

**理由**: FR-011、SC-005、ER-006、ER-006a；宪章 VI 新失败模式需检测与 runbook。

## 延后至实施任务的开放项（非产品未知项）

- 精确依赖版本锁定（`redis` Python 客户端、`react-router-dom`）在实施 PR 中经 lockfile 评审。
- 生产入口如何注入可信客户端 IP 的运维说明写入 runbook 任务，不阻塞本设计。
