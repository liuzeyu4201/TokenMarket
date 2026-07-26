# Tasks：手机号验证登录、会话签发与基础界面

**Input**: `specs/004-phone-login-session-ui/` 下的 `spec.md`、`plan.md`、
`research.md`、`data-model.md`、`contracts/` 与 `quickstart.md`

**Tests**: 本功能改变认证、安全、持久化、异步投递、运维和界面行为。所有行为实现前
必须先完成对应自动化测试并确认测试到达断言后因缺少目标 schema/行为而失败；不得把
collection、import、fixture-not-found、容器启动错误、跳过或重试到绿作为红灯证据。

**Organization**: US1、US2、US3 同为 P1，并共同组成首次可部署认证 MVP；只完成 US1
不是可部署 MVP。P1 发布门禁独立于 US4，但必须包含真实浏览器、性能、隐私、恢复和
不可变候选证据。US4 为 P2；P2 有代码变化时必须创建新候选并在其上重跑 P1 阻断证据。

## Format：`[ID] [P?] [Story] Description`

- **[P]**: 已满足阶段前置后，可与同组任务并行且不修改同一文件
- **[Story]**: 仅用户故事阶段使用 `[US1]`—`[US4]`
- 每项任务均包含明确文件路径

---

## Phase 1：Setup（契约、依赖与安全配置）

**Purpose**: 先建立共享契约、依赖治理和安全配置占位，不实现认证行为。

### 先写并确认失败的治理测试

- [X] T001 [P] 在 `tests/workflow/test_phone_auth_contracts.py` 添加 OpenAPI 3.1 解析、本地 `$ref`、4 个 operation、202-before-dispatch、稳定业务码、Cookie 不入正文及 Frontend 类型生成无漂移测试，并确认共享契约发布前到达断言后失败
- [X] T002 [P] 在 `tests/workflow/test_auth_dependency_policy.py` 添加准确 pin、lockfile、MIT/Apache-2.0 allowlist、维护元数据、传递依赖和 dev-only 范围测试，覆盖 `openapi-typescript@7.13.0`、`@vitejs/plugin-basic-ssl@2.3.0`、`testcontainers[postgres,redis]==4.14.2`，并确认实现前失败

### 建立契约与受控依赖

- [X] T003 将 `specs/004-phone-login-session-ui/contracts/` 发布到 `shared/contracts/phone-auth-session/v1/`，并在 `shared/contracts/README.md` 登记 owner、版本、兼容策略与 202-before-dispatch 语义，使 T001 的共享契约检查通过
- [X] T004 [P] 在 `frontend/package.json` 与 `frontend/package-lock.json` 准确锁定 `openapi-typescript@7.13.0`、`@vitejs/plugin-basic-ssl@2.3.0`，并增加可复现的 `generate:phone-auth-types` 与 drift-check scripts
- [X] T005 [P] 在 `services/api-service/pyproject.toml` 与 `services/api-service/uv.lock` 准确锁定 `testcontainers[postgres,redis]==4.14.2`，不得改写无关服务锁文件
- [X] T006 [P] 在 `.env.example` 与 `frontend/.env.development.example` 增加 session/OTP/CSRF/reference HMAC key version、trusted proxy CIDR、exact origin、SMS adapter、dispatcher lease/drain、cleanup schedule 与 TLS readiness 的安全占位
- [X] T007 在 `tools/workflow/dependency_policy.py`、`tools/workflow/security.py` 与根 `Makefile` 扩展现有 `security-check` 内部实现，使 T002 通过且不新增公开 Make 动作

**Checkpoint**: v1 契约和三个 dev-only 依赖可复现、可审计，认证端点仍不可用。

---

## Phase 2：Foundational（所有故事的阻断前置）

**Purpose**: 先建立可工作的真实依赖测试基础设施，再完成 HTTPS、同源、可信来源、
Foundation 隐私边界、密码学、数据约束、遥测与 coverage 门禁。

**⚠️ CRITICAL**: 本阶段全部通过前，不得开始或激活任何用户故事。

### 先建立并证明测试基础设施可用

- [X] T008 在 `services/api-service/tests/integration/conftest_authentication.py` 建立 testcontainers PostgreSQL 15.18、Redis 7.2、可控 DB clock、四类账户工厂、阻塞 SMS fake 与 dispatcher 夹具，并在 `services/api-service/tests/conftest.py` 通过 `pytest_plugins` 显式注册
- [X] T009 在 `services/api-service/tests/integration/test_auth_fixture_smoke.py` 验证 pytest collection、fixture resolution、PostgreSQL/Redis 版本与生命周期、DB clock、账户工厂和 fake adapter 可启动/回收；必须先通过本任务，后续 integration 红灯才有效

### 先写并确认失败的基础行为测试

- [X] T010 [P] 在 `services/api-service/tests/unit/test_auth_config.py` 覆盖 key current/previous、exact origin、trusted proxy、provider timeout、dispatcher lease/drain、cleanup 参数及 prod 缺 TLS/approved adapter/key 时 readiness fail-closed，并确认实现前失败
- [X] T011 [P] 在 `services/api-service/tests/unit/test_trusted_proxy.py` 覆盖不可信 peer 忽略 XFF、可信链右向左剥离、IPv4/IPv6 CIDR、malformed/null/unknown 来源回退或拒绝，并确认实现前失败
- [X] T012 [P] 在 `services/api-service/tests/unit/test_auth_http_security.py` 与 `tests/workflow/test_auth_privacy_sentinel.py` 仅覆盖 Foundation 的唯一 sentinel 词表/allowlist scanner，以及响应正文/非 `Set-Cookie` 响应头/log/error/metric/trace 序列化前零泄露；不得要求尚未实现的 DOM、Web Storage 或 BroadcastChannel，并确认实现前失败
- [X] T013 [P] 在 `services/api-service/tests/unit/test_auth_crypto.py` 覆盖 256-bit opaque token、OTP HMAC PRF rejection sampling、dispatcher 重算相同 6 位 OTP、`000000`/`012345`/`999999`、domain separation、常量时间比较、session-bound CSRF 与 current/previous/unknown key version，并确认实现前失败
- [X] T014 [P] 在 `tests/workflow/test_local_https_frontend.py` 与 `tests/workflow/test_auth_deploy_proxy.py` 覆盖 `make start` 五个 host processes、Vite HTTPS `/api` proxy、受限自签名探针、部署同源 `/api`/安全头/内部 healthcheck、dispatcher 生命周期及 `compose.local.yml` 无业务服务，并确认实现前失败
- [X] T015 [P] 在 `frontend/src/api/client.test.ts` 覆盖相对 `/api`、`credentials: "include"`、request ID、10 秒超时、统一 envelope 错误和禁止浏览器回退直连 API，并确认实现前失败
- [X] T016 [P] 在 `services/api-service/tests/unit/test_auth_observability_contract.py` 覆盖稳定低基数 metric/event 名称、request_id、安全 labels、序列化前 redaction 及 auth/provider/dispatcher/session/cleanup 告警所需信号，并确认实现前失败
- [X] T017 [P] 在 `tests/workflow/test_auth_coverage_gate.py` 添加根 `make test` 对 authentication domain/route 的 `pytest-cov` 80% line coverage fail-closed 测试，并确认 aggregate coverage 不能替代安全分支断言
- [X] T018 [P] 在 `services/api-service/tests/integration/test_phone_auth_migration.py` 覆盖 `0002→0003→0002→0003→head`、四表、dispatch lease/send-started 字段、FK/CHECK/index、partial unique 及禁止编辑既有迁移，并确认测试到达 schema 断言后失败
- [X] T019 [P] 在 `services/api-service/tests/integration/test_auth_model_constraints.py` 覆盖幂等唯一键、单 current challenge、pending/dispatching recovery index、send-started 状态、session 不可变字段、单 active session 与 audit `ON DELETE SET NULL`，并确认测试到达约束断言后失败

### 实现阻断基础

- [X] T020 在 `services/api-service/app/config.py`、`services/api-service/app/main.py` 与 `services/api-service/app/health.py` 实现认证配置、独立 readiness、精确 CORS/Origin 与 `no-store`，使 T010 通过
- [X] T021 [P] 在 `services/api-service/app/security/trusted_proxy.py` 与 `services/api-service/app/dependencies.py` 实现显式 CIDR、socket peer 和右向左可信代理链解析，并同步修复 SF03 注册限流来源，使 T011 通过
- [X] T022 [P] 在 `tests/workflow/auth_privacy_scanner.py` 与 `services/api-service/app/observability.py` 实现 sentinel allowlist scanner、HTTP/log/error/metric/trace 统一 redaction 和无 PII label 约束，使 T012 的 Foundation 边界通过
- [X] T023 [P] 在 `frontend/src/api/client.ts` 实现同源相对 URL、`credentials: "include"`、受控 headers、AbortController 超时与稳定业务错误解析，使 T015 通过
- [X] T024 在 `frontend/vite.config.ts`、`frontend/nginx.conf`、`tools/workflow/local_env/probes.py`、`tools/workflow/local_stack/processes.py` 与 `infra/docker/compose.app.yml` 实现本地/部署同源 HTTPS、`/api` proxy、安全头、内部 healthcheck 与 dispatcher 生命周期，使 T014 通过
- [X] T025 在 `services/api-service/app/domain/base.py`、`services/api-service/app/domain/users/models.py` 与 `services/api-service/app/domain/authentication/models.py` 建立共享 SQLAlchemy Base、四个认证实体、dispatch lease/send-started、22 小时 `delete_after`、关系与索引声明
- [X] T026 在 `services/api-service/alembic/versions/0003_phone_login_session.py` 实现 additive migration 与受保护反向删除顺序，使 T018/T019 通过
- [X] T027 在 `frontend/src/api/generated/phoneAuth.ts` 生成 v1 TypeScript 类型，并通过 `tests/workflow/test_phone_auth_contracts.py` 固定本地 schema 输入与 drift gate
- [X] T028 在 `services/api-service/app/security/otp.py`、`services/api-service/app/security/session.py` 与 `services/api-service/app/security/csrf.py` 实现无偏 OTP PRF/verification HMAC、opaque token、Cookie issue/clear 与 session-bound CSRF，使 T013 通过
- [X] T029 在 `services/api-service/Makefile`、`services/api-service/pyproject.toml` 与根 `Makefile` 接入 authentication domain/route 80% coverage 门禁，使 T017 通过且 CI 仍只调用根 `make ci`
- [X] T030 在 `services/api-service/app/observability.py` 建立低基数 auth/provider/dispatcher/session/cleanup metric/event registry，使 T016 通过

**Checkpoint**: 测试基础设施、HTTPS、可信来源、Foundation 隐私边界、迁移、密码学、
生成类型、遥测和 coverage 门禁全部通过。

---

## Phase 3：User Story 1 — 通过界面验证手机号并登录（Priority: P1）

**Goal**: 用户通过中性受理的手机号验证码流程建立唯一会话并进入基础受保护页。

**Independent Test**: 使用 active synthetic 账户和阻塞 fake adapter 请求 challenge；
adapter 未释放时 HTTP 202 已返回且 UI 不声称送达；释放后提交 leading-zero OTP，只建立
一个 60 分钟会话并进入 Dashboard，US1 隐私禁止面命中为零。

### Tests for User Story 1（先写并确认失败）

- [X] T031 [P] [US1] 在 `services/api-service/tests/unit/test_verification_domain.py` 覆盖 SF03 手机号规范化、5 分钟 challenge、最新 challenge、active/decoy、无明文 OTP 及只有 delivered eligible challenge 可验证，并确认实现前失败
- [X] T032 [P] [US1] 在 `services/api-service/tests/unit/test_sms_delivery.py` 覆盖 `SmsDeliveryPort` mapping、PRF 内存重算、stable provider ref、10 秒超时、无自动 resend、synthetic/prod 隔离、异常脱敏及 delivery outcome metric，并确认实现前失败
- [X] T033 [P] [US1] 在 `services/api-service/tests/contract/test_phone_login_contract.py` 覆盖两个 POST operation、202-before-dispatch、稳定业务码、Origin、幂等 header、leading-zero OTP、Set-Cookie 属性、正文无 credential 及既有 `/register` 兼容，并确认实现前失败
- [X] T034 [P] [US1] 在 `services/api-service/tests/integration/test_phone_login_happy_path.py` 覆盖 pending→dispatching→delivered、正确 OTP 原子消费、旧 challenge 失效、session 60 分钟、decoy 零会话与脱敏事件，并确认实现前失败
- [X] T035 [P] [US1] 在 `services/api-service/tests/integration/test_delivery_dispatcher.py` 覆盖并发 dispatcher 单 claim、lease 到期的 pre-send 恢复、`send_started_at` 后 query-or-invalidate、优雅停止、每 provider ref 最多一次 send 及 queue-age/claim/finalize metrics，并确认实现前失败
- [X] T036 [P] [US1] 在 `services/api-service/tests/unit/test_session_issue.py` 覆盖 user→challenge 固定锁序、OTP 消费、旧 session 撤销、新 session 插入、提交后 Cookie/CSRF 与冲突映射，并确认实现前失败
- [X] T037 [P] [US1] 在 `frontend/src/pages/Login.test.tsx` 覆盖手机号/OTP 提交、注册入口、中性 accepted、发送后聚焦 OTP、响应到达后 1 秒内可感知、站内目标恢复与进入 Dashboard，并确认实现前失败
- [X] T038 [P] [US1] 在 `frontend/src/auth/AuthContext.test.tsx` 覆盖登录结果只写入唯一 AuthContext、Login 不保存第二份 session 摘要、credential/CSRF 不持久化及 terminal state 清除 raw OTP，并确认实现前失败
- [X] T039 [P] [US1] 在 `frontend/src/pages/Login.privacy.test.tsx` 与 `tests/workflow/test_auth_privacy_sentinel.py` 覆盖手机号/OTP 仅在编辑中 input value 瞬时允许、提交后 OTP 清空、中性受理后只保留 masked phone、response body 与 Web Storage 零 sentinel，并确认实现前失败
- [X] T040 [P] [US1] 在 `services/api-service/tests/integration/test_auth_verify_performance.py`、`tests/workflow/fixtures/auth-browser/p1/` 与 `tests/workflow/test_auth_browser_p1_evidence.py` 覆盖固定 API 档案的 100 并发 verify/session p95≤500ms，以及使用合成 fixture 验证 P1 浏览器 20 次冷启动 p95≤3s、20 次旅程≤3min、candidate hash/版本/资源/离群值 evidence schema；测试不得读取真实 `evidence/browser-p1.md`，并确认实现前失败

### Implementation for User Story 1

- [X] T041 [P] [US1] 在 `services/api-service/app/schemas/authentication.py` 与 `services/api-service/app/errors.py` 实现 v1 challenge/session schema、字段错误和稳定业务码
- [X] T042 [P] [US1] 在 `services/api-service/app/sms/port.py`、`services/api-service/app/sms/synthetic.py` 与 `services/api-service/app/sms/fake.py` 实现 provider-neutral port、local synthetic、test blocking fake 与 prod fail-closed
- [X] T043 [US1] 在 `services/api-service/app/repositories/authentication.py` 实现 challenge/idempotency/session 固定锁序、202 结果提交、dispatch claim/lease/send-started/finalize 与安全 audit primitives
- [X] T044 [US1] 在 `services/api-service/app/domain/authentication/challenge_service.py` 实现 challenge 创建、旧 challenge supersede、decoy、公开 202 持久化和请求线程零 provider call
- [X] T045 [US1] 在 `services/api-service/app/domain/authentication/delivery_service.py` 实现用户/phone_ref 重检、OTP PRF 重算、accepted/rejected/timeout/unknown 最终化与禁止 resend
- [X] T046 [US1] 在 `services/api-service/app/dispatch/auth_delivery.py` 实现有界批量领取、lease、send-started、query-or-invalidate 恢复、指标与优雅停止，使 T032/T035 通过
- [X] T047 [US1] 在 `services/api-service/app/domain/authentication/session_service.py` 实现 OTP 校验、challenge 原子消费、旧 session 撤销、新 session 插入与提交后 Cookie/CSRF
- [X] T048 [US1] 在 `services/api-service/app/api/v1/auth.py` 接入 `POST /verification-challenges` 与 `POST /sessions`，保持 `/register` 兼容并使 T033/T034 通过
- [X] T049 [P] [US1] 在 `frontend/src/api/v1/phoneAuth.ts` 与 `frontend/src/types/auth.ts` 实现 generated types 驱动的 challenge/session facade 和可行动错误分类
- [X] T050 [US1] 在 `frontend/src/auth/AuthContext.tsx` 建立唯一 session 状态所有者与登录成功 transition，不读取 Cookie、不持久化 CSRF
- [X] T051 [US1] 在 `frontend/src/pages/Login.tsx` 实现手机号、OTP、中性 accepted、倒计时、登录、注册入口、in-flight 防重复、提交后清除 OTP 与安全站内 redirect
- [X] T052 [US1] 在 `frontend/src/pages/Dashboard.tsx` 与 `frontend/src/App.tsx` 接入 `/login`、受保护占位 `/dashboard` 和 AuthContext 登录结果，不加入业务 Dashboard
- [X] T053 [US1] 在 `services/api-service/app/observability.py` 与 `services/api-service/app/dispatch/auth_delivery.py` 接入 challenge/dispatch/session 的低基数 counter、duration、queue age 与脱敏 request_id 事件，使 T032/T034/T035 的遥测断言通过

**Checkpoint**: US1 可本地独立验证；US2、US3 与 P1 门禁完成前不得激活认证入口。

---

## Phase 4：User Story 2 — 拒绝无效、滥用或重放的登录尝试（Priority: P1）

**Goal**: 阻止猜测、重放、枚举、限流绕过与并发重复登录。

**Independent Test**: 对四类账户各请求 100 次并验证公开响应与 SC-006 时延无可区分
差异；同幂等键 100 并发只形成一个 winner，同 challenge 100 并发最多一个会话，US2
新增 URL/history/storage/中性 UI 隐私禁止面命中为零。

### Tests for User Story 2（先写并确认失败）

- [X] T054 [P] [US2] 在 `services/api-service/tests/unit/test_verification_attempts.py` 覆盖非 6 位 ASCII 不计次、错误 1—5 次、expired/locked/consumed/superseded 与 decoy 的统一动作，并确认实现前失败
- [X] T055 [P] [US2] 在 `services/api-service/tests/unit/test_auth_rate_limit.py` 覆盖 Redis Lua 双 ZSET、Redis TIME、phone 5/hour、IP 20/hour、HMAC key、winner 单计数、TTL、Redis down fail-closed 与 rate-limit metrics，并确认实现前失败
- [X] T056 [P] [US2] 在 `services/api-service/tests/integration/test_verification_idempotency.py` 覆盖同 key/phone 60 秒首次 202 重放、同 key 异 phone 冲突、过期 key、响应丢失、100 并发 winner 与 replay metrics，并确认实现前失败
- [X] T057 [P] [US2] 在 `services/api-service/tests/integration/test_verification_concurrency.py` 覆盖同 challenge 100 并发正确提交、双设备 100 轮并发登录、最终单 active session 与旧 session 1 秒内拒绝，并确认实现前失败
- [X] T058 [P] [US2] 在 `services/api-service/tests/integration/test_auth_anti_enumeration.py` 覆盖四类账户 status/code/message/shape 一致、provider-wide outage 一致、recipient detail 不透传、malformed phone 不查库/不投递及遥测无 PII，并确认实现前失败
- [X] T059 [P] [US2] 在 `services/api-service/tests/integration/test_sms_delivery_recovery.py` 覆盖 recipient accepted/rejected/timeout/unknown、send-started 后崩溃、status query、无法查询作废与绝不重发，并确认实现前失败
- [X] T060 [P] [US2] 在 `services/api-service/tests/integration/test_challenge_request_timing.py` 按 SC-006 固定档案对 active/unknown/suspended/deleted 各 100 次采样，断言每类 p95≤500ms、任意两类差≤100ms并记录低基数 duration；FR-004/ER-004 不维护独立阈值，并确认旧同步投递实现失败
- [X] T061 [P] [US2] 在 `frontend/src/pages/Login.security.test.tsx` 覆盖幂等键生命周期、60 秒倒计时、限流、验证码重试/重取、依赖不可用、中性文案与重复点击零额外调用，并确认实现前失败
- [X] T062 [P] [US2] 在 `frontend/src/pages/Login.privacy.test.tsx` 与 `tests/workflow/test_auth_privacy_sentinel.py` 增加 idempotency key/raw phone 不进入 URL/history/Web Storage、非 input DOM 或 neutral UI 的断言，并确认实现前失败

### Implementation for User Story 2

- [X] T063 [P] [US2] 在 `services/api-service/app/rate_limit.py` 与 `services/api-service/app/domain/authentication/rate_limit.lua` 实现 phone/IP HMAC rolling limiter 的单次 Lua 原子操作
- [X] T064 [US2] 在 `services/api-service/app/repositories/authentication.py` 实现持久幂等 processing/winner/replay/conflict/expired、60 秒中性 202 恢复与不重复限流
- [X] T065 [US2] 在 `services/api-service/app/domain/authentication/challenge_service.py` 实现 rolling cooldown、latest challenge、5 次锁定、格式错误不计次与 decoy 等时序状态机
- [X] T066 [US2] 在 `services/api-service/app/domain/authentication/delivery_service.py` 实现账户分支前 provider health epoch、recipient-specific 中性内部投影与失败清除 OTP material
- [X] T067 [US2] 在 `services/api-service/app/domain/authentication/session_service.py` 与 `services/api-service/app/repositories/authentication.py` 完成并发 challenge 消费、单 active session 与 partial unique 冲突安全映射
- [X] T068 [US2] 在 `services/api-service/app/api/v1/auth.py` 完成 validation/idempotency/rate-limit/provider-wide 业务码、`Retry-After` 与 anti-enumeration 映射
- [X] T069 [P] [US2] 在 `frontend/src/api/v1/phoneAuth.ts` 实现单次用户操作复用幂等键、同键重放和新操作换 key，且不把 raw phone/OTP/key 写入 URL 或持久存储
- [X] T070 [US2] 在 `frontend/src/pages/Login.tsx` 实现 resend deadline、业务码到字段/流程动作映射、中性提示、只显示 `phone_masked` 与安全重新开始路径
- [X] T071 [US2] 在 `services/api-service/app/observability.py` 与 `services/api-service/app/domain/authentication/challenge_service.py` 接入限流、重放、枚举投影、失败次数与 SC-006 时延遥测，使 T055/T056/T058/T060 通过

**Checkpoint**: US1+US2 安全登录路径完成，但缺少 US3 时仍只能关闭状态验证。

---

## Phase 5：User Story 3 — 维持、识别并安全结束会话（Priority: P1）

**Goal**: 刷新恢复会话、保护路由、新登录替换旧会话并安全幂等退出。

**Independent Test**: 登录后刷新仍 authenticated；设备 B 登录后设备 A 在 1 秒内被
拒绝；退出及重复退出安全成功，Cookie/CSRF/BroadcastChannel 禁止面零泄露。

### Tests for User Story 3（先写并确认失败）

- [X] T072 [P] [US3] 在 `services/api-service/tests/contract/test_session_contract.py` 覆盖 `GET/DELETE /session`、统一 envelope、Cookie issue/clear scope、`Cache-Control: no-store`、Origin/CSRF、401/403/503 与正文无 credential，并确认实现前失败
- [X] T073 [P] [US3] 在 `services/api-service/tests/unit/test_session_authentication.py` 覆盖 token version、unknown/expired/revoked/account-disabled、DB now、missing/wrong/cross-session CSRF、旧 Cookie 只定位自身与拒绝原因 metrics，并确认实现前失败
- [X] T074 [P] [US3] 在 `services/api-service/tests/integration/test_session_lifecycle.py` 覆盖刷新恢复、新登录替换、旧设备拒绝、账户状态重检、logout 响应丢失重试、进程重启及 bootstrap/revoke events，并确认实现前失败
- [X] T075 [P] [US3] 在 `services/api-service/tests/integration/test_session_fail_closed.py` 覆盖 DB down/unknown key version 返回 503、Redis down 不影响既有 session、受保护内容零泄漏，并确认实现前失败
- [X] T076 [P] [US3] 在 `frontend/src/auth/AuthContext.test.tsx` 覆盖 checking/authenticated/anonymous/unavailable、启动/focus bootstrap、内存 CSRF、401 清摘要与网络失败不误判登出，并确认实现前失败
- [X] T077 [P] [US3] 在 `frontend/src/auth/ProtectedRoute.test.tsx` 与 `frontend/src/layouts/AppShell.test.tsx` 覆盖无受保护内容闪现、站内目标恢复、logout、BroadcastChannel 只含事件名与 focus fallback，并确认实现前失败
- [X] T078 [P] [US3] 在 `services/api-service/tests/integration/test_session_performance.py` 按固定档案断言 session check 新增 p95≤50ms、logout/旧 session 拒绝≤1s、revocation visibility metric 与正确性不变量，并确认实现前失败
- [X] T079 [P] [US3] 在 `frontend/src/auth/AuthContext.privacy.test.tsx`、`services/api-service/tests/contract/test_session_contract.py` 与 `tests/workflow/test_auth_privacy_sentinel.py` 覆盖 Cookie 仅 wire-level `Set-Cookie` 瞬时允许、CSRF 仅内存、BroadcastChannel 仅安全事件名，以及 DOM/storage/log/evidence 零 sentinel，并确认实现前失败

### Implementation for User Story 3

- [X] T080 [US3] 在 `services/api-service/app/repositories/authentication.py` 实现按 token digest 查询 session+user、request-time 有效性、精确 session revoke 与旧 token 不影响新 token
- [X] T081 [US3] 在 `services/api-service/app/domain/authentication/session_service.py` 实现 bootstrap、账户状态检查、失效 Cookie 清除、Origin+CSRF 幂等 logout 与安全审计
- [X] T082 [US3] 在 `services/api-service/app/api/v1/auth.py` 接入 `GET /session` 与 `DELETE /session`，依赖不可确认时 fail-closed
- [X] T083 [P] [US3] 在 `frontend/src/api/v1/phoneAuth.ts` 实现 bootstrap/logout、CSRF header、401/403/503 分类与 credential 不可读约束
- [X] T084 [US3] 在 `frontend/src/auth/AuthContext.tsx` 扩展唯一四态 reducer、启动/focus revalidation、logout 与只广播安全事件名的跨标签同步
- [X] T085 [US3] 在 `frontend/src/auth/ProtectedRoute.tsx` 与 `frontend/src/App.tsx` 实现 checking guard、anonymous redirect、站内目标 allowlist 与 session 失效回登录
- [X] T086 [US3] 在 `frontend/src/layouts/AppShell.tsx` 实现 anonymous login/register 与 authenticated masked identity/role/dashboard/logout 导航，并在退出不确定时先 bootstrap
- [X] T087 [US3] 在 `services/api-service/app/observability.py` 与 `services/api-service/app/domain/authentication/session_service.py` 接入 bootstrap、拒绝原因、session 替换、撤销时延与 CSRF/Origin 遥测，使 T073/T074/T078 通过

**Checkpoint**: US1+US2+US3 形成 P1 功能闭环；完成 Phase 6 门禁后才可部署。

---

## Phase 6：P1 Deployable Authentication MVP Gates

**Purpose**: 在不依赖 US4 的前提下完成 cleanup、告警、恢复、不可变 candidate、P1
浏览器与真实部署预检。

### 先写并确认失败的 P1 跨领域测试

- [X] T088 [P] 在 `ops/tests/test_authentication_alerts.py` 逐项覆盖 auth readiness 连续 5m 不可用=Critical；服务/依赖失败率 10m >5% 且≥100=Warning、5m >20% 且≥50=Critical；provider rejected/timeout/unknown 10m >10% 且≥50=Warning、5m >25% 且≥25=Critical；oldest eligible work >30s 持续5m=Warning、>120s 持续5m=Critical；revocation p95 5m >1s 且≥20=Critical；cleanup 单次失败或 last-success>2h=Warning、连续3次失败或>4h或材料越过24h=Critical；due backlog >1h=Warning、>2h=Critical；owner、runbook 与连续两个恢复窗口，并确认规则实现前失败
- [X] T089 [P] 在 `services/api-service/tests/integration/test_auth_retention.py` 覆盖 challenge/OTP `expires_at+22h`、idempotency `created_at+22h`、session 90d、event 180d、500 行事务批次、900 秒预算、advisory lock、`already_running`、重复执行与 24h 硬期限，并确认实现前失败
- [X] T090 [P] 在 `tests/workflow/test_auth_cleanup_schedule.py` 覆盖 test/prod UTC `17 * * * *`、同版本 API image、稳定命令 `python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900`、本地同入口手动调用、无 startup loop/第二 wrapper/新公开 Make 动作及 2h/4h 告警，并确认配置实现前失败
- [X] T091 [P] 在 `tests/workflow/fixtures/auth-release/` 建立无 secret 的 valid/缺证据/hash 不符/digest 不符/synthetic-prod candidate fixtures，并在 `tests/workflow/test_auth_deploy_gate.py` 仅用这些 fixture 覆盖 TLS、approved SMS、trusted proxy/origin、keys、dispatcher、cleanup 与 evidence fail-closed；测试不得读取 `specs/004-phone-login-session-ui/evidence/`，并确认缺少门禁实现时失败
- [X] T092 [P] 在 `tests/workflow/test_auth_release_candidate.py` 覆盖 dirty-tree 拒绝、P1/P2 increment、commit/semantic version、全部 OCI/frontend digest、lock/contract hash、`.sha256` companion、evidence-only diff allowlist、绑定 evidence 缺失/篡改及 verify 不触发 build，并确认实现前失败
- [X] T093 [P] 在 `tests/workflow/test_auth_backup_restore.py` 添加隔离 PostgreSQL 15 真实 backup→fresh restore、脱敏 manifest、consumed/revoked/send-started/单 active 不变量与零 resend 测试，并确认实现前失败
- [X] T094 [P] 在 `tests/workflow/test_migrations.py` 覆盖 `0003` 的 API→Billing 顺序、forward/backout/retry/head restoration、破坏性 downgrade 审批及“head restoration 不等于数据 restore”，并确认 runbook/迁移门禁补齐前失败

### 实现 P1 运维、候选与恢复门禁

- [X] T095 在 `services/api-service/app/maintenance/auth_cleanup.py` 实现稳定入口 `python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900`、DB-now、`FOR UPDATE SKIP LOCKED`、advisory lock、每表每事务 500 行、15 分钟预算、22h/90d/180d 删除匿名化与脱敏 metrics，使 T089 通过
- [X] T096 在 `ops/schedules/authentication-cleanup.yml` 与 `infra/docker/compose.deploy.yml` 配置 test/prod UTC 每小时第 17 分钟以同版本 API image 调用 T095 的精确入口、本地禁用调度和并发单 owner，使 T090 通过
- [X] T097 在 `ops/alerts/authentication.yml` 与 `ops/runbooks/authentication.md` 实现 T088 逐项列出的所有窗口、阈值、最小样本、Warning/Critical、连续两个恢复窗口、API Service authentication on-call owner、dispatcher/cleanup 分流诊断与保数据回滚
- [X] T098 在 `tools/workflow/release_candidate.py` 与 `tools/workflow/cli.py` 实现 `workflow release-candidate capture|verify`、candidate JSON/`.sha256`、digest/lock/contract 绑定、evidence-only diff allowlist与 verify 禁止重建，使 T092 通过且不新增公开 Make 动作
- [X] T099 在 `tools/workflow/deploy_env/lifecycle.py` 与 `infra/docker/compose.app.yml` 实现与真实 evidence 路径解耦的 auth activation fail-closed、dispatcher/cleanup/readiness 及 candidate/evidence verifier，使 T091 的合成 fixture 测试通过且不泄露 secret
- [X] T100 在 `tools/workflow/auth_backup_restore.py` 实现隔离数据库 backup、fresh restore、脱敏 manifest 与认证不变量校验，使 T093 通过
- [X] T101 在 `ops/runbooks/migrations.md` 纳入 `0003` 发布顺序、backout/retry/head restoration、数据 restore 区分与破坏性 downgrade 审批，使 T094 通过

### 构建一次并执行绑定 P1 证据

- [ ] T102 在 clean source commit 上依次运行根目录 `make toolchain-check`、`make bootstrap` 与一次 `make ci`，随后运行 `uv run --project tools/workflow --locked workflow release-candidate capture --increment p1 --output specs/004-phone-login-session-ui/evidence/candidate-p1.json` 生成 candidate 与 `candidate-p1.sha256`，并把脱敏门禁结果写入 `specs/004-phone-login-session-ui/evidence/quality-gates-p1.md`；此后禁止修改 source/contract/lock 或重建
- [ ] T103 [P] 仅在 T102 candidate 上执行 `services/api-service/tests/integration/test_auth_verify_performance.py`、`test_challenge_request_timing.py` 与 `test_session_performance.py` 的固定档案，并将 candidate SHA/digest、资源、样本与结果写入 `specs/004-phone-login-session-ui/evidence/api-performance-p1.md`
- [ ] T104 [P] 仅在 T102 candidate 上按 `specs/004-phone-login-session-ui/quickstart.md` 第 10 节执行 P1 浏览器旅程、20 次冷启动 p95≤3s、20 次旅程均≤3min、无受保护内容闪现、站内 redirect、Cookie/CSRF 不持久化及全禁止面 sentinel 零命中，并写入 `specs/004-phone-login-session-ui/evidence/browser-p1.md`
- [ ] T105 [P] 仅在 T102 candidate 上按 `specs/004-phone-login-session-ui/quickstart.md` 第 13 节执行真实 backup→fresh restore，并将 candidate SHA/digest、工具版本、时间与脱敏不变量写入 `specs/004-phone-login-session-ui/evidence/backup-restore-p1.md`
- [ ] T106 [P] 仅在 T102 candidate 上按 `specs/004-phone-login-session-ui/quickstart.md` 第 5—11 节执行契约、leading-zero OTP、幂等、dispatcher、CSRF、双 Cookie jar、旧设备、logout、cleanup、逐项告警与故障矩阵，并写入 `specs/004-phone-login-session-ui/evidence/quickstart-p1.md`
- [ ] T107 在 `specs/004-phone-login-session-ui/evidence/traceability-p1.md` 建立全部 P1 FR/ER/SC→task→自动化/人工 evidence 映射，引用 T102 candidate SHA，并确认 P1 不依赖 US4
- [ ] T108 在 T103—T107 全部完成后运行 `uv run --project tools/workflow --locked workflow release-candidate verify --manifest specs/004-phone-login-session-ui/evidence/candidate-p1.json` 与 `make deploy mode=test auth_release_manifest=specs/004-phone-login-session-ui/evidence/candidate-p1.json`，验证 source commit→HEAD 仅 evidence diff、全部 hash/digest 绑定及真实 test preflight，结果写入 `specs/004-phone-login-session-ui/evidence/deploy-preflight-p1.md` 且不得执行 `make build`/`make ci`
- [ ] T109 在 `specs/004-phone-login-session-ui/evidence/release-readiness-p1.md` 汇总 candidate、依赖许可证、配置/迁移、dispatcher/cleanup/alert health、性能、恢复、浏览器、真实 preflight、rollback decision point 与真实 SMS 未就绪时的生产阻断结论

**Checkpoint**: T001—T109 全部通过时，US1+US2+US3 才是可部署 P1；不等待 US4。

---

## Phase 7：User Story 4 — 使用一致且可访问的基础认证界面（Priority: P2）

**Goal**: 在 P1 闭环上补齐完整状态、320px、仅键盘与 WCAG 2.2 AA。

**Independent Test**: 仅键盘在 320px 完成发送、leading-zero OTP 登录与退出；全状态可
感知、无横向滚动，普通文本≥4.5:1，大号文本/控件/状态边界/焦点≥3:1。

### Tests for User Story 4（先写并确认失败）

- [X] T110 [P] [US4] 在 `frontend/src/pages/Login.accessibility.test.tsx` 覆盖 visible label、`aria-describedby`、`aria-invalid`、busy/status/alert、错误焦点、OTP text/inputMode/autocomplete 与键盘顺序，并确认实现前失败
- [X] T111 [P] [US4] 在 `frontend/src/pages/Login.states.test.tsx` 覆盖 idle/requesting/accepted/countdown/verifying/success/field-error/code-error/expired/rate-limited/unavailable 全状态，并确认实现前失败
- [X] T112 [P] [US4] 在 `frontend/src/auth/challengeState.test.ts` 覆盖只保存 challenge id/phone_masked/绝对时间、刷新恢复、服务端时钟权威、terminal/logout/invalidation 清理及禁止 raw phone/OTP/CSRF/user summary，并确认实现前失败
- [X] T113 [P] [US4] 在 `frontend/src/layouts/AppShell.accessibility.test.tsx` 覆盖语义导航、身份/角色/退出状态、焦点返回与匿名/认证动作不重复，并确认实现前失败
- [X] T114 [P] [US4] 在 `frontend/src/styles/globals.accessibility.test.ts`、`tests/workflow/fixtures/auth-browser/p2/` 与 `tests/workflow/test_auth_browser_p2_evidence.py` 覆盖 WCAG 2.2 AA 普通文本4.5:1、大号文本/控件/状态边界/焦点3:1、disabled/inactive 例外清单、320px、仅键盘100%及合成 candidate-bound evidence schema；测试不得读取真实 `evidence/browser-p2.md`，并确认实现前失败

### Implementation for User Story 4

- [X] T115 [US4] 在 `frontend/src/pages/Login.tsx` 完成语义表单、字段关联、焦点管理、读屏低噪声状态与 leading-zero OTP 输入，使 T110/T111 通过
- [X] T116 [P] [US4] 在 `frontend/src/auth/challengeState.ts` 实现绝对期限计算、允许字段 sessionStorage adapter、刷新恢复及 terminal/logout/invalidation 清理，使 T112 通过
- [X] T117 [US4] 在 `frontend/src/styles/globals.css` 实现 320px 无横向滚动、可见 focus、busy/disabled/error/success 及 WCAG 2.2 AA 对比度，使 T114 的 token/ratio 断言通过
- [X] T118 [US4] 在 `frontend/src/layouts/AppShell.tsx` 与 `frontend/src/pages/Dashboard.tsx` 完成一致导航、受保护占位与可访问 logout 状态，使 T113 通过

**Checkpoint**: US4 自动化验收通过；真实浏览器 P2 证据必须等待 Phase 8 新候选。

---

## Phase 8：P2 Release Gates

**Purpose**: 为包含 US4 的代码生成新 P2 candidate，在该候选上重跑 P1 阻断证据并完成
P2 真实浏览器与部署预检；不得复用不同 digest 的 P1 evidence。

- [ ] T119 在 clean P2 source commit 上依次运行根目录 `make toolchain-check`、`make bootstrap` 与一次 `make ci`，随后运行 `uv run --project tools/workflow --locked workflow release-candidate capture --increment p2 --output specs/004-phone-login-session-ui/evidence/candidate-p2.json` 生成 candidate 与 `candidate-p2.sha256`，并写入 `specs/004-phone-login-session-ui/evidence/quality-gates-p2.md`；此后禁止修改 source/contract/lock 或重建
- [ ] T120 [P] 仅在 T119 candidate 上重跑 T103—T106 的全部 P1 性能、浏览器、恢复、隐私、cleanup/alert 和 quickstart 阻断矩阵，并将 candidate-p2 SHA/digest 绑定结果写入 `specs/004-phone-login-session-ui/evidence/p1-regression-on-p2.md`；只有全部 digest 与 P1 相同才可引用旧证据
- [ ] T121 [P] 仅在 T119 candidate 上按 `specs/004-phone-login-session-ui/quickstart.md` 第 10 节执行真实浏览器 P2 全状态、320px、仅键盘100%、刷新、多标签、computed-color 与焦点检查，并把 candidate SHA/digest 与 WCAG 2.2 AA 结果写入 `specs/004-phone-login-session-ui/evidence/browser-p2.md`
- [ ] T122 在 `specs/004-phone-login-session-ui/evidence/traceability-p2.md` 建立 US4/FR-025/ER-007/SC-010→T110—T121→自动化/浏览器 evidence 映射，并引用 T119 candidate 与该候选上的 P1 regression
- [ ] T123 在 T120—T122 全部完成后运行 `uv run --project tools/workflow --locked workflow release-candidate verify --manifest specs/004-phone-login-session-ui/evidence/candidate-p2.json` 与 `make deploy mode=test auth_release_manifest=specs/004-phone-login-session-ui/evidence/candidate-p2.json`，验证 evidence-only diff、全部 hash/digest 绑定及真实 test preflight，结果写入 `specs/004-phone-login-session-ui/evidence/deploy-preflight-p2.md` 且不得执行 `make build`/`make ci`
- [ ] T124 在 `specs/004-phone-login-session-ui/evidence/release-readiness-p2.md` 汇总 P2 candidate、P1-on-P2 gates、US4 全状态、320px、仅键盘、WCAG 2.2 AA、privacy sentinel、浏览器、真实 preflight 与 rollback decision point

**Checkpoint**: T119—T124 全部通过后才可发布 P2 UI。

---

## Requirement Traceability

| Requirement keys | Primary tasks |
|---|---|
| FR-001—FR-003 | T031, T033, T037, T041, T048, T051, T058, T068 |
| FR-004—FR-005 | T033, T034, T044, T058, T060, T066 |
| FR-006—FR-007 | T013, T028, T031—T034, T054, T065, T115 |
| FR-008—FR-008c | T011, T021, T055, T056, T061—T064, T068, T069 |
| FR-009—FR-011 | T031, T034, T036, T047, T054, T057, T065, T067 |
| FR-011a—FR-012 | T019, T025, T034, T036, T057, T067 |
| FR-012a—FR-013a | T012, T013, T022, T028, T033, T038, T072—T085 |
| FR-014—FR-015 | T072—T078, T080—T087, T106 |
| FR-016—FR-018 | T001—T007, T010, T012, T015, T027, T032, T033, T042, T091, T099, T106 |
| FR-019—FR-021 | T037, T051, T058, T061, T070, T077, T085, T110, T111, T115 |
| FR-022—FR-024 | T052, T074—T077, T084—T086, T106, T113, T118 |
| FR-025 | T110—T118, T121 |
| FR-026—FR-026a | T018, T019, T032, T035, T043, T045, T046, T058, T059, T066, T068 |
| ER-001—ER-003 | T001—T003, T012—T019, T022, T025—T028, T031—T036, T072—T075, T093, T100 |
| ER-004—ER-005 | T032, T035, T040, T057, T059, T060, T074, T075, T078, T103—T106 |
| ER-006 | T016, T030, T032, T034, T035, T053, T055, T056, T058, T060, T071, T073, T074, T078, T087, T088, T097 |
| ER-007 | T110—T121 |
| ER-008 | T006, T010, T016, T025, T088—T090, T095—T097, T106 |
| SC-001—SC-002a | T013, T031, T033, T034, T054, T057, T074, T078, T106 |
| SC-003—SC-005 | T037, T040, T051, T052, T072—T078, T085, T104, T106 |
| SC-006—SC-007a | T011, T021, T055—T060, T063, T064, T069, T103 |
| SC-008—SC-009 | T012, T022, T032, T038, T039, T061, T062, T069, T072—T079, T104, T106 |
| SC-010 | T110—T121 |
| SC-011 | T088—T090, T095—T097, T106 |

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundation
    ├─ T008 fixture/plugin → T009 smoke PASS → T018/T019 integration red tests
    ↓
Phase 3 US1
    ├──────────────→ Phase 4 US2
    └──────────────→ Phase 5 US3
Phase 3 + Phase 4 + Phase 5
    ↓
Phase 6 P1 Gates
    ├─ T088—T094 tests → T095—T101 implementation
    └─ T102 build/capture → T103—T107 bound evidence → T108 preflight → T109 readiness
    ↓
P1 deployable

Phase 3 + Phase 5 interfaces stable
    ↓
Phase 7 US4
    ↓
Phase 8 P2 Gates
    └─ T119 build/capture → T120—T122 bound evidence → T123 preflight → T124 readiness
    ↓
P2 deployable
```

### User Story Dependencies

- **US1 (P1)**: Foundation 后开始；提供 challenge、dispatcher、session 签发和最小 UI。
- **US2 (P1)**: 依赖 US1 surface；可与 US3 并行，但完成前登录不得激活。
- **US3 (P1)**: 依赖 US1 已签发 session；与 US2 并行，完成后形成 P1 功能闭环。
- **P1 Gates**: 依赖 US1+US2+US3，不依赖 US4。
- **US4 (P2)**: 依赖 US1 Login 与 US3 AuthContext/AppShell 接口稳定；不修改 P1 安全语义。
- **P2 Gates**: 依赖 P1 与 US4；US4 代码产生新 candidate 时，必须在 P2 digest 上重跑
  P1 阻断证据。

### Within Each Phase

1. T008/T009 必须先通过；后续 integration 红灯必须到达断言并因 schema/行为缺失失败。
2. 各阶段 test tasks 先于对应实现；Models/security primitives 先于 repository，
   repository 先于 domain service，domain service 先于 route。
3. Generated types 先于 handwritten facade；AuthContext 是唯一 session 状态所有者。
4. 隐私边界依次为 Foundation→US1→US2→US3→P1 aggregate，不得提前虚构未来 surface。
5. T102/T119 各自只运行一次 `make ci` 并 capture；之后只做 digest-bound evidence，
   T108/T123 最后 preflight，禁止重建。
6. 不得用 aggregate coverage 替代安全、并发、恢复、迁移和失败分支直接断言。

## Parallel Opportunities

- Setup 的 T001/T002、T004—T006 可按文件并行。
- Foundation 中 T008→T009 串行；T009 通过后 T010—T019 可按文件并行编写红灯。
- US1 的 T031—T040 可并行；T041/T042/T049 修改不同边界，可并行。
- US2 的 T054—T062 可并行；T063 与 T069 可并行。
- US3 的 T072—T079 可并行；T080 与 T083 可并行。
- P1 的 T088—T094 可并行；T103—T106 在同一 candidate 上使用隔离环境/文件时可并行。
- US4 的 T110—T114 可并行；T116 可与 Login/CSS/AppShell 实现并行。
- P2 的 T120/T121 可在同一 candidate 上使用隔离环境和不同 evidence 文件并行。

### Parallel Example：US1

```text
Task T031: services/api-service/tests/unit/test_verification_domain.py
Task T032: services/api-service/tests/unit/test_sms_delivery.py
Task T033: services/api-service/tests/contract/test_phone_login_contract.py
Task T035: services/api-service/tests/integration/test_delivery_dispatcher.py
Task T037: frontend/src/pages/Login.test.tsx
Task T039: frontend/src/pages/Login.privacy.test.tsx
```

### Parallel Example：US2

```text
Task T054: services/api-service/tests/unit/test_verification_attempts.py
Task T055: services/api-service/tests/unit/test_auth_rate_limit.py
Task T056: services/api-service/tests/integration/test_verification_idempotency.py
Task T058: services/api-service/tests/integration/test_auth_anti_enumeration.py
Task T060: services/api-service/tests/integration/test_challenge_request_timing.py
Task T062: frontend/src/pages/Login.privacy.test.tsx
```

### Parallel Example：US3

```text
Task T072: services/api-service/tests/contract/test_session_contract.py
Task T073: services/api-service/tests/unit/test_session_authentication.py
Task T076: frontend/src/auth/AuthContext.test.tsx
Task T077: frontend/src/auth/ProtectedRoute.test.tsx
Task T079: frontend/src/auth/AuthContext.privacy.test.tsx
```

### Parallel Example：US4

```text
Task T110: frontend/src/pages/Login.accessibility.test.tsx
Task T111: frontend/src/pages/Login.states.test.tsx
Task T112: frontend/src/auth/challengeState.test.ts
Task T113: frontend/src/layouts/AppShell.accessibility.test.tsx
Task T114: frontend/src/styles/globals.accessibility.test.ts
```

## Implementation Strategy

### P1 Deployable Authentication MVP（US1 + US2 + US3）

1. 完成 Setup。
2. 完成 Foundation，尤其先通过 T008/T009，再编写有效 integration 红灯。
3. 完成 US1，并只在本地暗置验证异步投递和登录。
4. 并行完成 US2 防滥用与 US3 会话闭环。
5. 完成 P1 运维实现；在 clean source commit 上只构建一次并 capture P1 candidate。
6. 在该 candidate 上采集全部证据，最后执行真实 preflight。
7. **STOP AND VALIDATE**: 仅 T001—T109 全部通过时才可部署 P1；不等待 US4。

US1 或 US1+US2 只能作为关闭状态的本地技术预览，不是可部署 MVP。

### P2 Complete Authentication UI

1. 在 US1 Login 与 US3 AuthContext/AppShell 接口稳定后完成 US4。
2. 在 clean P2 source commit 上只构建一次并 capture 新 candidate。
3. 在 P2 candidate 上重跑全部 P1 阻断证据，再采集 P2 浏览器证据。
4. 最后执行 P2 真实 preflight 和 release-readiness 汇总。
5. **STOP AND VALIDATE**: T119—T124 全部通过后发布 P2。

### Parallel Team Strategy

1. 团队共同完成 Setup + Foundation。
2. US1 surface 稳定后，US2 与 US3 可由不同人员并行。
3. 运维工作可在 US1—US3 期间准备 T088—T094 红灯，但实现等待测试确认失败。
4. US3 前端接口稳定后可实现 US4；P1/P2 candidate 生成后的 evidence 不得与源码修改并行。

## Notes

- `[P]` 只表示文件和已完成依赖不冲突，不代表可跳过阶段前置。
- 自动生成文件只由锁定脚本产生，不手工编辑 `frontend/src/api/generated/phoneAuth.ts`。
- `.env.*`、真实手机号、OTP、Cookie、CSRF、provider/key 材料不得提交或写入 evidence。
- wire-level `Set-Cookie` 与用户编辑中的 input value 是受限瞬时 allowlist，不得输出到
  测试日志；其余禁止面 sentinel 命中必须为零。
- candidate/evidence 可形成纯 evidence commit；source commit→HEAD 只允许
  `specs/004-phone-login-session-ui/evidence/` 变化。
- 正常应用回滚保留 additive `0003` 表；migration head restoration 不等于数据 restore。
- 没有批准的真实 SMS adapter 时，生产认证必须保持不可用。

---

## Phase 9: Convergence

**Purpose**: Close gaps between spec/plan intent and the current codebase after
`/speckit-implement`. Existing open tasks T040 and T102–T109 / T119–T124 already
track missing performance fixtures and P1/P2 candidate evidence; this phase covers
**false-complete** work and functional gaps not already queued.

**Order**: CRITICAL/HIGH first. Complete before treating the feature as deployable.

- [X] T125 CRITICAL Fix `tools/workflow/local_stack/processes.py` so local `make start` does not inject `VITE_API_BASE_URL` to a direct API host; frontend auth must use same-origin relative `/api` under Vite HTTPS, and update local HTTPS probes/`tests/workflow/test_local_https_frontend.py` accordingly per plan same-origin topology / FR-012a / T023–T024 (`contradicts`)
- [X] T126 HIGH Wire `frontend/src/api/v1/phoneAuth.ts` (and register if cookie-bearing) through `getBrowserAuthBaseUrl` / auth-safe URL resolution so browser session traffic cannot silently use a cross-origin `VITE_API_BASE_URL` per FR-012a / cookie-csrf contract (`partial`)
- [X] T127 HIGH Add `frontend/src/pages/Login.security.test.tsx` covering idempotency-key lifecycle, 60s countdown, rate-limit/retry UX, neutral anti-enumeration copy, and zero extra in-flight challenge calls per US2/FR-019 / T061 (`partial`)
- [X] T128 HIGH Complete false-complete T114 automation: add `frontend/src/styles/globals.accessibility.test.ts`, `tests/workflow/fixtures/auth-browser/p2/`, and `tests/workflow/test_auth_browser_p2_evidence.py` with WCAG token/ratio + candidate-bound evidence schema (must not read real `evidence/browser-p2.md`) per FR-025 / SC-010 / T114 (`partial`)
- [X] T129 HIGH Ensure full SC-006 challenge-timing profile (100 samples × 4 account classes, p95≤500ms, inter-class Δ≤100ms) is executable as the acceptance path for evidence (default CI may stay light, but `TM_PERF=1` / release evidence must run full profile and not treat n=5 as SC-006 pass) per SC-006 / FR-004 (`partial`)
- [X] T130 HIGH Strengthen dual-device concurrency coverage so 100 login rounds each leave exactly one active session and old sessions are rejected within 1s per SC-002a / FR-011a / FR-015 (`partial`)
- [X] T131 MEDIUM Expand `tests/workflow/test_local_https_frontend.py` and `tools/workflow/local_env/probes.py` / `local_stack` assertions for five host processes under `make start`, self-signed HTTPS probe, and API dispatcher lifecycle flags (beyond static Vite/nginx string checks) per plan T014 (`partial`)
- [X] T132 MEDIUM Add or relocate authentication alert contract tests to the path promised by T088 (`ops/tests/test_authentication_alerts.py` or an equivalent registered suite) so every plan.md alert window/threshold/sample/owner is asserted, not only schedule/runbook string presence per T088 / plan observability (`partial`)
- [X] T133 MEDIUM Ensure optional live backup→restore path for auth tables is documented and greened under a single explicit env gate (`AUTH_BACKUP_TEST_DATABASE_URL`) with redacted manifests before T105 evidence relies on it per SC-011 / Constitution III restore evidence (`partial`)
- [X] T134 LOW Review `ProductionBlockedSmsAdapter` / approved-adapter placeholder so production never silently becomes usable without a real approved SMS port implementation, and document the fail-closed readiness matrix in runbook per FR-016 (`partial`)

**Note**: Do not re-implement open tasks T040 (verify-performance + browser-p1 fixtures/schema) or T102–T109 / T119–T124 (candidate evidence capture). After this phase, re-run `/speckit-converge` if needed.
