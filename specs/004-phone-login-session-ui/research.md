# Phase 0 Research：手机号验证登录、会话签发与基础界面

**Feature**: `004-phone-login-session-ui`

**Date**: 2026-07-25
**Status**: Complete — 所有研究问题均已解决

## Decision 1：边界保持在现有 API Service、Frontend 与共享契约

**Decision**: 手机验证码、挑战消费、会话签发/校验/撤销、认证审计由
`services/api-service/` 拥有；React 界面和浏览器内认证摘要由 `frontend/` 拥有；
设计期契约位于本功能 `contracts/`，实现时提升到
`shared/contracts/phone-auth-session/v1/`。Proxy Gateway、Billing Service 与 Admin
Service 不增加认证业务逻辑，也不访问 API Service 数据库。

**Rationale**: 用户身份已经由 API Service 的 `users` 领域拥有。继续使用现有边界可
复用 SF03 的用户、手机号规范化、统一包络、PostgreSQL/Redis 连接和 UI 壳层，并符合
宪章 I 的服务所有权要求。

**Alternatives considered**:

- 新建 identity-service：V0.1 规模不足以承担新服务、部署和 ADR 成本。
- 把浏览器认证放入 Go Gateway：会把领域认证和短信工作流塞进入口热路径，越过现有职责。
- 由 Frontend 自行判断身份：客户端状态不能成为认证或授权事实。

## Decision 2：采用 PostgreSQL 状态化 opaque session，而不是 JWT

**Decision**: 登录成功生成至少 256-bit CSPRNG 随机凭证，Cookie 只携带
`<key-version>.<opaque-secret>`。PostgreSQL `auth_sessions` 保存独立 UUID
`session_id`、用户、角色快照、时间与撤销事实，以及使用外部版本化 key 计算的
`HMAC-SHA-256` token digest；不保存原始凭证。验证只接受 current/previous key
version，未知或缺失 key 一律失败关闭。

**Rationale**: 本规格要求每次受保护请求都检查撤销状态和当前账户状态，因此 JWT 仍要
查询持久会话，无法获得无状态收益。Opaque token 避免算法/claim 漂移和新认证依赖，
同时让数据库泄漏者无法直接使用凭证；Python 标准库 `secrets`、`hmac`、`hashlib`
已足够。

**Alternatives considered**:

- JWT：仍需数据库撤销查询，还增加算法白名单、签名库和 key rotation 复杂度。
- 只保存 SHA-256：高熵 token 本身足够抗枚举，但 HMAC 可进一步隔离数据库泄漏。
- Redis-only session：Redis flush/restart 可能使撤销事实倒退，违反宪章 III。

## Decision 3：单 active 会话在一个短事务中签发

**Decision**: 验证正确验证码时按固定顺序锁定 user 与 challenge，在同一 PostgreSQL
事务内完成 challenge 消费、撤销该用户所有 `revoked_at IS NULL` 旧 session、插入
新 session 和安全审计事件；提交成功后才设置 Cookie。数据库以
`UNIQUE(user_id) WHERE revoked_at IS NULL` 作最后防线，新登录先撤销自然过期但尚未
标记的旧行。

**Rationale**: 该事务直接保证同一验证码最多消费一次、并发登录最终只有一个 active
会话，并让旧设备下一次数据库校验立即失败，满足 1 秒撤销目标。

**Alternatives considered**:

- 应用层先 revoke 后 insert：并发实例存在双会话竞态。
- Redis 分布式锁：锁丢失不能替代数据库不变量。
- challenge 消费与 session 创建分开提交：崩溃会留下“验证码已消费但无会话”状态。

## Decision 4：使用 `__Host-` Secure Cookie 和同源浏览器入口

**Decision**: 会话 Cookie 名称为 `__Host-tokenmarket_session`，属性固定为
`Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600`，不设置 `Domain`。签发、
过期和清除必须使用完全一致的作用域；所有认证响应设置 `Cache-Control: no-store`。
浏览器统一通过 HTTPS 同源 `/api`：本地 Vite HTTPS 代理到 loopback API，部署时
Frontend Nginx `/api` 反向代理到 API Service，公开生产入口必须位于获批准的 TLS
边缘之后。

**Rationale**: `__Host-` 防止子域放宽 Domain/Path，HttpOnly 降低 XSS 直接读取凭证
风险；同源交付显著缩小 CORS、Cookie 与 CSRF 配置差异，并修复当前生产静态包默认
指向浏览器自身 `127.0.0.1:8000` 的问题。

**Alternatives considered**:

- local 使用 `Secure=false`：直接违反已澄清的 FR-012a。
- 依赖浏览器对 HTTP localhost 的例外：不同浏览器/地址不可复现。
- Bearer + Web Storage：已被规格明确排除。

## Decision 5：本地 HTTPS 是实现门禁，不新增长期服务

**Decision**: Frontend 增加经评审并锁定的 Vite basic-SSL 开发插件，由现有 Vite
进程提供自签名 HTTPS 和 `/api` proxy；`make start` 仍保持五个 host application
processes，不增加 Compose 服务。workflow 前端探针和输出相应改用 HTTPS，并只对这个
明确的本地自签名端点采用受控证书例外。生产容器内部 healthcheck 仍可使用 loopback
HTTP；浏览器公开入口必须由外部 TLS edge 提供 HTTPS。

**Rationale**: 这既满足 Secure Cookie，又不引入额外反向代理进程或系统工具安装。
新增插件由 npm lock 固定，符合 bootstrap 只安装 committed-lock dependencies 的要求。

**Alternatives considered**:

- 要求开发者安装 `mkcert`/OpenSSL：违反 bootstrap 不安装系统工具的可复现边界。
- 提交私钥/证书：违反秘密与凭证治理。
- 新增本地 TLS Compose 服务：扩大 SF02 依赖集，违反当前 Compose 范围。

## Decision 6：CSRF 使用 Origin 校验 + 绑定 session 的同步 token

**Decision**: 服务端以独立版本化 key 对当前 `session_id` 计算确定性 HMAC CSRF token；
登录成功与 `GET /api/v1/auth/session` 在响应 body 返回该 token，Frontend 仅内存保存。
所有依赖 Cookie 身份的状态变更必须同时满足：

1. `Origin`（必要时严格 `Referer` fallback）精确命中允许列表；
2. `X-CSRF-Token` 与当前 session 重新计算值常量时间相等。

验证码请求/验证虽然不依赖已有 Cookie，也执行 Origin allowlist 防 login-CSRF。

**Rationale**: 该方案不需要保存 CSRF 明文或另设 JavaScript-readable Cookie，页面刷新
可重新 bootstrap，同一 session 的多个标签不会互相轮换失效。SameSite 仅是纵深防线。

**Alternatives considered**:

- SameSite-only：FR-013a 明确禁止。
- 朴素 double-submit：增加可读 Cookie，且容易遗漏与 session 的绑定。
- 数据库存 CSRF 明文：不符合敏感材料最小化。

## Decision 7：精确 CORS、凭证请求与安全头

**Decision**: Frontend `fetch` 固定 `credentials: "include"`；优先同源相对 `/api`。
若存在受控跨 origin 测试，CORS 只允许显式 origin、`GET/POST/DELETE/OPTIONS` 与
`Content-Type`、`X-Request-ID`、`Idempotency-Key`、`X-CSRF-Token`，禁止通配符。
Cookie、`Set-Cookie`、`X-CSRF-Token`、验证码与完整手机号在进入日志前统一删除/
脱敏，不记录 request headers 的未知字段。

**Rationale**: 当前 API 使用 credentials CORS 但 methods/headers 为 `*`，现有
`redact_headers()` 也没有屏蔽 Cookie/CSRF；认证功能上线前必须收紧这两个边界。

**Alternatives considered**:

- 保持通配 CORS：凭证请求的信任边界不可审计。
- 继续 blacklist 少数 header：新增敏感 header 时容易漏记，安全 allowlist 更稳妥。

## Decision 8：可信代理链从右向左解析

**Decision**: 新增显式 trusted-proxy CIDR 配置。只有 socket peer 位于可信 CIDR 时才
解析转发链，并从最右端向左剥离可信代理、选择第一个非可信地址；peer 不可信时完全
忽略客户端 `X-Forwarded-For`。链格式非法时使用可验证 peer 或拒绝，不得跳过 IP
限流。Uvicorn/入口的 proxy-header 信任范围同步收紧。

**Rationale**: 当前 `client_ip()` 无条件使用 XFF 最左值，可被直连客户端任意伪造，
直接违反 FR-008c。该改动也会同步修正 SF03 注册限流的相同缺陷。

**Alternatives considered**:

- 总取 XFF 最左值：可绕过限流。
- 总取 socket peer：部署在代理后会让所有用户共享一个桶。
- 设备指纹：用户已选择 IP 维度，且设备指纹增加隐私与稳定性成本。

## Decision 9：OTP 采用版本化 HMAC，不使用无钥哈希

**Decision**: challenge id 由 CSPRNG 生成；验证码使用版本化 OTP derivation key 对
`otp-send:v1 || challenge-id || counter` 执行 HMAC-SHA-256，并以 rejection sampling
无偏映射到 `000000..999999`。请求事务和异步 dispatcher 可按 challenge id/key version
在进程内重算相同 6 位值，数据库不保存明文或可逆 ciphertext。数据库只保存独立
domain-separated verification HMAC、salt 与 key version，提交验证时常量时间比较。
terminal challenge 立即清空 digest，其余在过期后最多 24 小时清除；仍被非终态
challenge 引用的 key version 不得移除，readiness 在缺失时失败关闭。

**Rationale**: 6 位验证码仅有 100 万种，无钥 SHA 即使加盐也可离线穷举。HMAC 让
数据库单独泄漏不足以验证猜测；domain-separated PRF 使 dispatcher 无需保存可直接使用
的验证码即可异步投递。rejection sampling 消除直接取模偏差，在线尝试仍受 5 次锁定和
双维度限流约束。

**Alternatives considered**:

- 明文或可逆加密：数据库泄漏可直接恢复验证码。
- 仅保存随机验证码的不可逆 digest：异步 dispatcher 无法取得实际短信内容。
- SHA-256 + salt：仍可快速枚举全部空间。
- Argon2/bcrypt：安全但增加依赖和并发 CPU 成本，短期 OTP 不需要。

## Decision 10：持久幂等、rolling cooldown 与 Redis Lua 限流

**Decision**:

- PostgreSQL `verification_request_idempotency` 先以 HMAC key digest 获得处理权；同键
  同 phone_ref 在 60 秒内重放首次结果、不重新限流/创建/投递；同键异手机号 409；
  窗口后旧键过期，记录最多 24 小时清理。
- user row 与最近 challenge 锁保证两个不同 key 对同手机号的 rolling 60 秒冷却和
  “只有最新 challenge 可用”。
- Auth 专属 Redis Lua 一次原子处理 phone/IP 两个 rolling 1 小时 ZSET；阈值分别
  5/20，key 使用 HMAC reference 而非原手机号/IP，Redis `TIME` 为窗口时钟。幂等
  replay 不重复计数，Redis 不可用则验证码请求 503 fail-closed。

**Rationale**: PostgreSQL 保证跨进程重启的幂等首次结果，Redis 承担高频可丢失防滥用
状态；Lua 避免当前注册 limiter 的 15 分钟固定窗、原始 PII key 和双维度非原子问题。

**Alternatives considered**:

- Redis SETNX 幂等：重启/flush 丢失首次结果。
- 当前 `INCR+EXPIRE` 注册 limiter：窗口和隐私语义均不符合 SF04。
- PostgreSQL-only 限流：攻击流量会直接占用数据库。

## Decision 11：公开 202 与投递解耦，由 PostgreSQL durable dispatcher 恢复

**Decision**: HTTP 请求线程在 provider-wide health、幂等和限流通过后，以一个短事务
持久化首次中性 202 结果、pending challenge、`provider_request_ref` 与 dispatch work，
提交后立即返回；它不得调用 recipient-specific SMS adapter。API Service 内部 dispatcher
使用 `FOR UPDATE SKIP LOCKED` 和有界 lease 领取 pending work，在真正调用前先提交
`dispatching` / `send_started_at` 事实，然后以稳定 `provider_request_ref` 最多调用一次
SMS port。明确 accepted 转为 delivered；rejected/timeout/unknown 清除 code digest 并
转为 delivery_failed。崩溃后：

- lease 过期且尚无 `send_started_at` 的 work 可被重新领取；
- 已有 `send_started_at` 的 work 禁止再次 send，只能按 provider ref 查询；
- 供应商不支持查询或结果仍不确定时作废并告警。

dispatcher 与 Web 进程同属 API Service 生命周期，但不是请求内任务或仅内存队列；停止
时先停止领取新 work，再在有界窗口内完成/标记当前 work。

**Rationale**: 公开路径不等待 recipient-specific 供应商，才能同时满足统一 202 时延与
反枚举。`send_started_at` 之前可安全恢复，之后宁可作废也不重复发送，明确承认数据库与
外部短信不存在原子 exactly-once。

**Alternatives considered**:

- 在数据库事务内等待 HTTP：长事务/连接耗尽，仍不能获得原子性。
- 请求线程提交 Tx1 后同步调用 adapter 再响应：会引入账户类别时序侧信道。
- 只用进程内 queue：崩溃会丢失 pending work。
- timeout 后自动 retry：可能发送重复短信。
- 宣称 outbox exactly-once：没有 provider 幂等能力时是假保证。

## Decision 12：供应商选择留在已明确的采购范围外，但 adapter contract 固定

**Decision**: 本功能实现 `SmsDeliveryPort`、确定性 fake 与 ignored local/test
synthetic adapter；生产模式发现 synthetic、缺少获批准 adapter 或缺少 secret 时认证
readiness 失败关闭。真实供应商 adapter 只有在商业审批后按
[contracts/sms-delivery.md](./contracts/sms-delivery.md) 独立评审加入；在此之前不得
激活生产手机号登录。

**Rationale**: 产品规格明确排除短信供应商采购，计划不能虚构 vendor API。先固定
安全语义和 fail-closed gate，既能完成本地/自动化验证，也不会把 synthetic code
带入生产。

**Alternatives considered**:

- 现在随意选择 vendor：缺少商业、合规和凭证决策。
- 提供通用任意 URL webhook：难以定义幂等、错误和隐私边界。
- 生产自动回退 synthetic：规格和宪章明确禁止。

## Decision 13：反枚举优先于暴露 recipient-specific 投递结果

**Decision**: 所有格式合法手机号在中性结果和 pending challenge 提交后、任何
recipient-specific 调用前获得相同 202 包络、opaque `challenge_id`、脱敏显示和倒计时；
ineligible 账户使用 `user_id IS NULL` 的不可签发 decoy challenge。对外只允许
provider-wide availability 产生统一 `DELIVERY_UNAVAILABLE`；recipient-specific reject
发生在异步 dispatcher 中，不能改变已经返回的公开结果，challenge 在内部失败且不可用。
Provider health epoch 必须在账户分支前确定并应用到所有请求。

**Rationale**: 这是同时满足 FR-004 防枚举和 FR-026 依赖失败反馈的可执行边界。攻击者
不能通过 code/message/status 区分 active、unknown、suspended、deleted；真实用户可在
60 秒后重新获取或通过 request_id 报障。

**Alternatives considered**:

- 未知号立即 success、active provider failure 返回 503：可直接枚举。
- 给未知号发送短信：造成骚扰、费用和隐私问题。
- 返回明确 `ACCOUNT_UNAVAILABLE`：违反规格。

## Decision 14：Frontend 使用 Context 四态、ProtectedRoute 与绝对时间

**Decision**:

- `AuthProvider/useAuth` 使用 `checking | authenticated | anonymous | unavailable`，
  仅内存保存脱敏摘要与 CSRF token；启动、窗口 focus 和受保护入口调用
  `GET /session`。
- `/login` 和中性 `/dashboard` 加入现有壳层；ProtectedRoute 在 checking 时不渲染
  受保护内容，anonymous 通过 Router state 保存站内目标，登录后仅恢复该内部目标。
- 发送成功返回 `challenge_id`、`phone_masked`、`expires_at`、
  `resend_available_at`；倒计时每次按服务端绝对时间重算。`sessionStorage` 只保存这些
  无凭证 challenge 元数据，不保存原始/完整手机号、验证码、用户摘要、CSRF 或 session；
  terminal state、logout 或 session invalidation 时全部清除。
- 同源标签通过 `BroadcastChannel` 只广播 login/logout/invalidation 事件，接收方重新
  bootstrap；无支持时以 visibility/focus 重验降级。

**Rationale**: 四态防止网络故障被误判为登出和受保护内容闪现；绝对时间抵抗后台 timer
节流；Router state 避免开放重定向；原生 Context/BroadcastChannel 无需新运行时依赖。

**Alternatives considered**:

- Zustand/TanStack Query：当前状态规模不值得增加依赖。
- URL redirect query：更容易形成开放重定向。
- 1 秒前端轮询：浪费资源，也不能替代服务端撤销保证。

## Decision 15：界面、错误与可访问性契约

**Decision**: OTP 控件使用 text + numeric input mode + one-time-code autocomplete，保留
前导零并仅提示 ASCII 6 位；字段有 visible label、`aria-describedby`、
`aria-invalid`，busy 区使用 `aria-busy`，错误为 alert。发送成功聚焦验证码；格式错误
聚焦可修字段；倒计时只在关键变化使用 polite status，不每秒播报。业务码映射为：
字段修复、验证码可重试、challenge 过期/耗尽需重新获取、限流/依赖稍后重试、
unauthenticated 清 session、CSRF invalid 重新 bootstrap。

P2 视觉验收采用 WCAG 2.2 AA：普通文本对比度至少 4.5:1，大号文本至少 3:1，交互控件、
状态边界和可见焦点指示器至少 3:1；disabled/inactive 例外必须显式记录。自动化检查
语义、状态和受控 design token，真实浏览器证据复核最终计算颜色、键盘与 320px。

隐私扫描使用唯一 sentinel 并采用 allowlist：用户编辑期间只允许 raw phone/OTP 出现在
对应输入控件自身 value；wire-level `Set-Cookie` 只允许出现在发往目标浏览器的响应头，
契约测试可在进程内瞬时断言但不得输出。其他 DOM/attribute、响应正文、其他响应头、
URL/history、Web Storage、BroadcastChannel、日志、异常、metric、trace、analytics、
snapshot、backup 与 evidence 出现 sentinel 均失败。提交后清空 OTP，中性受理后只显示
`phone_masked`；Cookie 属性测试与泄露扫描分开执行，避免把必要交付误报为泄露。

**Rationale**: 复用现有 Register 表单模式并直接满足 320px、键盘、前导零和错误可行动
要求；不能用 `type=number`，否则会吞掉前导零。

**Alternatives considered**:

- 只按 HTTP status：无法表达“重试验证码”与“重新获取”的差异。
- 直接展示任意服务端 message：可能泄露信息或随实现漂移。
- 每秒 aria-live：造成读屏噪声。

## Decision 16：契约优先与 schema-checked Frontend 类型

**Decision**: 设计期创建一个 OpenAPI、业务码、Cookie/CSRF 和 SMS port 文档；实现时
提升至 `shared/contracts/phone-auth-session/v1/`，不修改 registration v1。锁定
`openapi-typescript` dev dependency，生成 `frontend/src/api/generated/phoneAuth.ts`；
手写 `frontend/src/api/v1/phoneAuth.ts` 只作为 typed facade 消费生成类型。AuthContext
是 session 摘要与 CSRF 的唯一前端所有者，Login 只拥有 challenge 表单状态。CI 检查
生成无漂移；API contract tests 验证 202 在 dispatcher send 前返回、Cookie 和错误码。

**Rationale**: 宪章要求 HTTP contract 在消费者前定义，Frontend 使用 generated 或
schema-checked types。单一版本化 surface 避免重复 envelope，也保持 SF03 兼容。

**Alternatives considered**:

- 继续手写类型：容易与 OpenAPI 漂移。
- 把 SF04 endpoint 加入 registration v1：混合不同责任和版本生命周期。
- 只写 Markdown：无法提供机器校验。

## Decision 17：测试先于实现，并以分层自动化和真实浏览器证据闭环

**Decision**:

- 测试基础设施先于依赖它的行为测试：先准确 pin `testcontainers`、注册 pytest plugin，
  建立 PostgreSQL 15.18/Redis 7.2、可控数据库时钟、账户工厂、阻塞 SMS fake 与
  dispatcher 夹具，并用最小 smoke test 证明 collection、fixture resolution 和容器
  lifecycle 正常。随后迁移/集成测试才可作为红灯；红灯必须到达断言并因缺失 schema 或
  行为失败，import、fixture-not-found、container bootstrap 或 collection error 不算
  测试先行证据。基础设施本身不是业务行为实现。
- pytest unit：OTP/token/CSRF HMAC、key rotation、Cookie、Origin、可信代理、状态机、
  错误与日志脱敏。
- PostgreSQL 15 + Redis 7 integration：迁移 forward/backout/retry、100 并发 challenge
  消费、双设备登录、幂等 winner、rolling limit、dispatcher lease/crash/unknown、
  provider timeout、重启、清理调度与保留。
- Vitest + Testing Library：AuthProvider 四态、ProtectedRoute、AppShell、Login、
  absolute countdown、idempotency reuse、fetch credentials/CSRF、错误焦点和
  BroadcastChannel。
- Quickstart 使用两个 curl cookie jar 与真实本地 UI 验证 Cookie、刷新、旧设备下线、
  320px、键盘和多标签，并按固定浏览器验收档案记录 20 次冷启动与完整旅程样本。当前
  不引入 Playwright；不得把 jsdom 当成真实 Cookie 浏览器证据。
- 所有安全/行为实现前先提交并确认至少一个相关测试因缺失行为而失败；CSRF 直接负向测试
  必须先于 CSRF 实现。根 `make test` 必须执行 authentication domain/route 的
  `pytest-cov` 并以 80% 行覆盖率 fail closed，aggregate coverage 不能代替关键分支断言。
- 部署同源代理、dispatcher/业务遥测、告警和隐私扫描同样属于行为变更；其失败测试必须在
  配置或指标实现前出现，不得集中到实现完成后的最终阶段补写。
- 隐私扫描按 surface 分层。Foundation 只测试 sentinel 词表/allowlist 扫描器与后端
  HTTP、日志、异常、metric、trace 序列化原语；US1 测输入 value 生命周期、提交后 OTP
  清空、response body 与 Web Storage；US2 测 idempotency/raw phone 的 URL/history、
  storage 和中性 UI；US3 测 Cookie/CSRF、BroadcastChannel 和多标签；P1 真实浏览器
  evidence 聚合扫描所有禁止面。Foundation 不得要求尚未存在的 DOM/Web Storage/
  BroadcastChannel 行为通过。
- API 基准对四类账户各采样 100 次，记录 p95 和任意两类差值；UI 状态测试证明验证结果
  1 秒内呈现，真实浏览器档案证明首屏 p95 ≤3 秒及完整旅程 ≤3 分钟。

**Rationale**: 现有仓库没有浏览器 runner。新增 Playwright 会增加浏览器二进制、
bootstrap/cache 和 CI 责任；分层自动化加显式手工证据可覆盖当前 V0.1 范围。

**Alternatives considered**:

- 只做 happy path/aggregate coverage：不满足宪章 V 的安全与并发负测。
- 只用 fake DB/Redis：无法证明行锁、partial unique 与 Lua 原子性。
- 隐式加入 Playwright：依赖和工作流成本未经过评审。

## Decision 18：清理由部署平台触发，保留、恢复与发布证据独立验证

**Decision**:

- 到期判断始终在请求路径执行；cleanup 只负责空间与保留合规。challenge/idempotency
  最多 24 小时，session 过期/撤销后 90 天，security event 180 天；cleanup 小批量、
  幂等、可观测，不在 startup 隐式运行。测试和生产在 UTC 每小时第 17 分钟调用 API
  Service 一次性命令，每次最多运行 15 分钟、每事务最多 500 行；数据库 advisory lock
  保证单一执行者，本地只手动调用。challenge/OTP 使用失效或过期后 22 小时的
  `delete_after`，幂等记录使用创建后 22 小时，为小时级调度和运行预算预留缓冲。
- cleanup 的稳定逻辑入口固定为
  `python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900`。
  test/prod scheduler 在与 API Service 相同版本的镜像内执行该命令；本地运维人员从
  API Service 的 locked 环境显式手动调用同一入口。入口输出只含 run id、outcome、
  rows-by-entity、duration 和 oldest-due-age 等脱敏字段；advisory lock 未取得时以
  `already_running` 成功退出。不得新增公开 Make action、startup loop 或复制业务逻辑
  的第二 wrapper。
- 新增低基数 auth request/verification/session/replay/CSRF/provider counters 与 duration
  histogram，以及 dispatcher pending/leased/dispatching/unknown age 指标；无
  phone/IP/session labels。新增 `ops/alerts/authentication.yml` 和
  `ops/runbooks/authentication.md`，owner 为 API Service。
- 固定告警：auth readiness 连续 5 分钟不可用为 Critical；服务/依赖失败率 10 分钟
  >5% 且 ≥100 eligible 请求为 Warning、5 分钟 >20% 且 ≥50 请求为 Critical；
  provider rejected/timeout/unknown 比率 10 分钟 >10% 且 ≥50 dispatch 为 Warning、
  5 分钟 >25% 且 ≥25 dispatch 为 Critical；最老 eligible work >30 秒持续 5 分钟为
  Warning、>120 秒持续 5 分钟为 Critical；revocation visibility p95 在 5 分钟内
  >1 秒且 ≥20 样本为 Critical。
- cleanup 单次失败或 last-success >2 小时为 Warning；连续 3 次失败、last-success
  >4 小时、或认证材料越过 24 小时硬期限为 Critical；due backlog 最老年龄 >1 小时为
  Warning、>2 小时为 Critical。恢复需连续两个评估窗口低于阈值。
- 任务与告警测试必须逐项抄录上述每个窗口、阈值、最小样本数、severity、owner、
  连续两个恢复窗口和 runbook 链接；“覆盖所有阈值”之类汇总表述不构成可执行计划。
- Alembic `0003_phone_login_session` 只 additive。发布顺序为 migration → API →
  same-origin frontend → auth activation；正常 app rollback 保留新表。真正 downgrade
  会删除认证/审计数据，必须先停流量、撤销 session、取得保留决策，并在隔离
  PostgreSQL 15 完成真实备份→恢复→认证不变量复核；migration head restoration 不能
  代替数据 restore test。

**Rationale**: 安全语义不能依赖清理；additive migration 允许旧 app 忽略新表；告警与
runbook 覆盖 provider、rate-limit、CSRF 和 auth availability 新故障面。

**Alternatives considered**:

- startup cleanup/create_all：启动副作用和不可审计 schema 变更。
- 立即 downgrade 作为常规 rollback：会破坏会话和审计保留。
- 指标用 phone/IP label：产生 PII 与高基数风险。

## Decision 19：新增依赖必须先完成维护、许可证和可复现性评审

**Decision**: 计划期选择三个 dev-only 依赖：

- `openapi-typescript@7.13.0`（MIT），用于从本地 OpenAPI 生成 runtime-free 类型；
- `@vitejs/plugin-basic-ssl@2.3.0`（MIT），仅用于现有 Vite 本地 HTTPS；
- `testcontainers[postgres,redis]==4.14.2`（Apache-2.0），用于 Python 3.11 下的真实
  PostgreSQL/Redis 集成测试。

实现前先增加会失败的 lock/drift/license 测试，再准确 pin manifest 与 lockfile，记录
上游发布活跃度、许可证、传递依赖和为何现有依赖不能满足；security/license scan 必须
通过。上述版本与元数据来自 2026-07-25 查验的
[npm openapi-typescript](https://www.npmjs.com/package/openapi-typescript)、
[npm basic SSL plugin](https://www.npmjs.com/package/@vitejs/plugin-basic-ssl) 与
[PyPI testcontainers](https://pypi.org/project/testcontainers/)。

**Rationale**: 三者分别保护契约生成、本地 Secure Cookie 和真实依赖测试，均不进入
生产 runtime；准确 pin 和评审证据满足宪章的最小依赖与可复现要求。

**Alternatives considered**:

- 手写 OpenAPI 类型：会漂移且不可机器验证。
- 降级 Secure Cookie 或继续 HTTP：违反安全规格。
- 用 fake DB/Redis：不能验证 PostgreSQL 锁、约束和 Redis Lua。
- 引入通用认证或浏览器自动化框架：当前范围没有足够收益。

## Decision 20：性能与发布证据绑定一次构建的不可变候选

**Decision**: Quickstart 固定两套可复现档案：

- API 档案：Linux 或 macOS、至少 4 vCPU/8 GiB、PostgreSQL 15.18 与 Redis 7.2 的
  已锁定镜像、API host process、synthetic adapter、5 次预热；四类账户各 100 次请求，
  以及 100 并发 verify/session，记录命令、commit、工具链、资源与 p50/p95/max。
- Browser 档案：同一 commit 的 production frontend build、无 CPU/network throttling、
  清缓存冷启动 20 次，记录浏览器准确版本、设备/CPU/内存、navigation/mark 时间；首屏
  p95 ≤3 秒，完整合成旅程 20 次均 ≤3 分钟。UI fake-timer 测试另行证明验证结果在
  1 秒内进入可感知状态。

结果写入脱敏 evidence；达不到阈值即失败，不得通过改变样本或删除离群值制造通过。
SC-006 是账户不可枚举性能验收的规范性 acceptance source；FR-004 与 ER-004 中相同的
500ms/100ms 文字只描述该约束的功能和工程投影。计划、任务和 evidence 统一引用
SC-006，避免三处独立阈值在后续维护中漂移。

发布门禁按增量拆分。P1 必须完成 US1+US2+US3、全部后端/安全/恢复/cleanup 门禁，以及
真实浏览器中的 protected-content 无闪现、Cookie/CSRF 不持久化、站内 redirect、
刷新/退出、结果 1 秒可感知、首屏 p95≤3 秒和 20 次旅程均≤3 分钟。P2 在 P1 仍通过的
同一候选 artifact 上增加 US4 完整状态矩阵、320px、仅键盘完成率 100%、焦点/ARIA 和
WCAG 2.2 AA；P1 不依赖 US4，但不得把 SC-003/SC-004 的浏览器性能推迟到 P2。

每个 increment 必须采用以下不可变顺序：

1. 冻结源代码并运行一次根 `make ci`；失败则修复后重新开始。
2. 在不修改源码或重建的前提下，生成 `evidence/candidate-p1.json` 或
   `candidate-p2.json`，记录 increment、commit SHA、semantic version、clean-tree
   assertion、全部应用 OCI digest、production frontend artifact/image digest、
   lock/contract hash，并把 JSON 的 SHA-256 写入同 basename 的 `.sha256` companion。
3. API performance、真实浏览器、privacy、backup/restore、cleanup/alert 与
   traceability evidence 全部引用 manifest SHA-256 和精确 digest。
4. 最后运行真实 deploy readiness preflight，核对 HEAD、manifest、证据 hash 与将部署
   digest；最终校验不得重跑 `make build`。

任一 source、lock、contract 或 digest 变化都会使已绑定证据失效。US4 代码变化会产生
新的 P2 candidate，P1 阻断证据必须在该候选上重跑；只有 P1/P2 digest 完全相同才可复用。
部署门禁的自动化测试使用隔离的无 secret 合成 candidate/evidence fixture，只验证
fail-closed 逻辑，不读取或伪装真实 P1/P2 evidence；真实 preflight 必须在全部实际证据
生成后执行。candidate 与 evidence 最后可以作为纯证据提交落库；preflight 必须证明
manifest 的 source commit 到当前 HEAD 之间只有该 feature 的 `evidence/` 文件发生变化，
否则不得把后来修改的 source/lock/contract 与旧 digest 混为同一候选。

**Rationale**: 阈值只有与资源、预热、样本量和测量点绑定才可复现，也避免把外部短信
到达时间混入 API/界面自身性能。

**Alternatives considered**:

- 只记录一次人工感受：不可复现。
- 用 jsdom wall-clock 代表真实首屏：不代表浏览器加载。
- 不记录环境的本机 p95：无法比较回归。
- 先做浏览器证据再运行 `make build`：后续构建可能改变实际发布制品，使证据失去对象。
- 让门禁单测依赖真实 evidence 文件：造成测试与人工执行顺序循环，也无法稳定构造负例。

## Research Gate Result

所有技术上下文未知项均已解析。以下不是未决问题，而是实现/发布硬门禁：

1. 本地必须先完成 Vite HTTPS + `/api` proxy 与 workflow probe 适配，禁止 Secure
   Cookie 降级。
2. `client_ip()` 必须改为 trusted-proxy 解析，并同步 SF03 runbook/tests。
3. Cookie、CSRF、OTP、手机号与 idempotency headers 必须在序列化前脱敏。
4. 生产缺 TLS edge、approved SMS adapter 或外部版本化 key 时 auth readiness 失败关闭。
5. PostgreSQL/Redis 实测必须证明统一 202 的四类 p95/差值、50ms session 增量、
   500ms verify/sign p95 和并发不变量；计划不提前宣称性能通过。
6. dispatcher、部署清理调度、≥80% coverage 和隔离数据库备份恢复证据均为发布阻断项。
7. 新依赖必须先通过维护、许可证、lock/drift 和最小化评审。
8. P1 发布门禁不依赖 US4，但必须包含浏览器功能/性能/凭证边界；P2 才增加完整状态、
   320px、键盘和 WCAG 2.2 AA。
9. cleanup 固定小时级 cadence、15 分钟预算、500 行事务批次与 22 小时 delete_after
   缓冲；告警阈值和隐私 sentinel allowlist 均不得留给实现自行猜测。
10. pytest/testcontainers fixture 与 plugin 注册先于迁移/集成红灯；红灯必须是断言失败，
    不能是 collection 或环境错误。
11. cleanup scheduler 与本地手工操作复用稳定的 `python -m
    app.maintenance.auth_cleanup` 一次性入口；告警任务逐项写明窗口、样本和 severity。
12. 每个 P1/P2 increment 只构建一次并生成 digest-bound candidate manifest；所有真实
    evidence 之后产生，deploy preflight 最后执行且不得触发重建。
