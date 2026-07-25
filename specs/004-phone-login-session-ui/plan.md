# Implementation Plan：手机号验证登录、会话签发与基础界面

**Branch**: `004-phone-login-session-ui` | **Date**: 2026-07-25 | **Spec**: [spec.md](spec.md)

**Input**: `specs/004-phone-login-session-ui/spec.md`

## Summary

在既有 SF03 注册能力上，由 API Service 提供手机号验证码挑战、验证码核验、单 active
浏览器会话签发、会话恢复与登出；Frontend 提供登录页、受保护的 Dashboard、会话启动
检查和基础可访问界面。浏览器凭证采用服务端状态化 opaque session，通过
`Secure`、`HttpOnly`、`SameSite=Lax` 的 `__Host-` Cookie 传递，配合精确 Origin 校验
和 session-bound CSRF token；PostgreSQL 保存挑战、幂等和会话事实，Redis 只承担
rolling 限流。验证码请求在 PostgreSQL 提交中性 202 结果与 pending challenge 后立即
返回，由 API Service 内部 dispatcher 异步领取、投递和恢复，不等待 recipient-specific
供应商结果。首次可部署增量必须同时完成 US1、US2、US3；实现前必须先完成同源 HTTPS、
本地可信代理链、凭证 CORS、敏感头脱敏和测试优先门禁，生产环境在真实短信 adapter、
TLS 与密钥配置就绪前 fail closed。

## Technical Context

**Language/Version**: Python 3.11.15；TypeScript strict、React 18.3.1；Node.js 24.18.0

**Primary Dependencies**: FastAPI 0.139.2、Starlette 1.3.1、SQLAlchemy 2.0.37、
asyncpg 0.30、Alembic 1.14.1、Pydantic 2.10.6、redis-py 5.2.1；React Router
7.18.1、Vite 8.1.4、Vitest 4.1.10。计划期评审的开发依赖为
`openapi-typescript@7.13.0`、`@vitejs/plugin-basic-ssl@2.3.0`（均 MIT）和
`testcontainers[postgres,redis]==4.14.2`（Apache-2.0）；实现时必须以准确 pin 写入
对应 manifest/lockfile，并记录维护活跃度、许可证、传递依赖与最小化理由。会话与 OTP
使用 Python 标准库 `secrets`、`hmac`、`hashlib`，不引入 JWT 或通用认证框架。

**Storage**: PostgreSQL 15.18 是用户、验证码挑战、请求幂等、会话和安全事件的事实源；
Redis 7.2 仅保存可重建的手机号/IP rolling 限流桶；Frontend 不持久化原始/完整手机号、
OTP、session token 或 CSRF token。`sessionStorage` 只允许保存 challenge id、脱敏手机号
和服务端绝对期限，并在 terminal state、logout 或 session invalidation 时清除。

**Testing**: pytest、pytest-asyncio、testcontainers、真实 PostgreSQL/Redis 集成与并发
测试；Vitest、React Testing Library；OpenAPI/schema 生成检查；根 Makefile 的
`make type-check`、`make lint`、`make test`、`make security-check`、`make ci`；真实
浏览器 quickstart 证据。每项行为任务必须先有可确认失败的测试；Python authentication
domain/route 通过仓库工作流执行 `pytest-cov` 且行覆盖率至少 80%，安全、并发、恢复和
迁移分支保留直接断言。测试基础设施是行为测试的前置而非被测业务实现：必须先完成
pytest plugin 注册、testcontainers PostgreSQL/Redis、可控时钟和 fake adapter 夹具，
确认测试可被正常收集并到达断言，再编写因 schema/行为缺失而失败的迁移与集成测试；
不得把 import、fixture-not-found、容器启动或 collection error 当作“红灯”证据。

**Target Platform**: Linux 服务端与 OCI 镜像；现代桌面/移动浏览器；macOS/Linux 本地
开发环境通过受控 HTTPS 同源入口访问。

**Project Type**: 现有 monorepo Web 应用；FastAPI API Service + React Frontend。

**Performance Goals**: active、unknown、suspended、deleted 各 100 次验证码请求
p95 均 ≤500 ms 且任意两类 p95 差值 ≤100 ms；100 个并发登录流程下验证码核验并
签发会话 p95 ≤500 ms；已认证请求的会话校验新增开销 p95 ≤50 ms；95% 验证结果在
提交后 1 秒内呈现、95% 登录首屏在 3 秒内可交互，完整登录—刷新—退出旅程在 3 分钟
内完成；撤销后的旧会话在 1 秒内失效。基准必须记录固定验收配置、预热、样本量和原始
脱敏摘要。账户不可枚举的 100 次/500ms/100ms 验收以 SC-006 为唯一规范性 acceptance
source；FR-004 与 ER-004 只引用该同一约束的功能/工程投影，不维护独立阈值。

**Constraints**: OTP 固定为 6 位 ASCII 十进制数字、允许前导零、5 分钟有效且最多
5 次错误尝试；请求验证码按手机号 5 次/小时、可信客户端公网 IP 20 次/小时并带
60 秒幂等重放窗口；会话有效期 60 分钟且每用户最多一个 active session；Cookie
不得进入响应体、Web Storage、日志或前端状态；生产环境缺失真实短信投递、TLS、
HMAC key 或可信代理配置时必须 fail closed。

**Scale/Scope**: 4 个公开认证端点、2 个页面、1 个前端认证上下文、1 个 API Service
内部 dispatcher 和 1 个由部署平台触发的一次性清理命令；新增 4 张 PostgreSQL 表和
2 类 Redis 限流桶；复用现有 `users` 表与 API Service，不新增常驻服务。短信供应商
采购、刷新令牌、第三方登录、账号恢复、RBAC 和业务 Dashboard 内容不在本范围。

### Affected Components

| Component | Owner / Planned change | Explicit non-change |
|---|---|---|
| `services/api-service/` | 认证领域、挑战/幂等/会话仓储、内部 durable dispatcher、短信投递 port、可信代理解析、CSRF、迁移、清理、遥测和测试 | 不跨服务读取数据，不承担短信供应商采购，不新增长期服务 |
| `frontend/` | 同源 HTTPS、generated types、手写 API facade、唯一 AuthContext、登录页、ProtectedRoute、Dashboard、登出、可访问性和测试 | 不读取 Cookie，不持久化敏感认证事实，Login 不建立第二份 session 状态 |
| `shared/contracts/phone-auth-session/v1/` | 实现时发布经批准的 OpenAPI、业务码、Cookie/CSRF 和 SMS port 契约 | 不修改既有 registration v1 语义 |
| `tools/workflow/`、`tests/workflow/`、根 `.env.example` | 校验本地 HTTPS、可信代理、认证配置、依赖治理、authentication coverage、性能档案与备份恢复；调整现有启动/探针适配 HTTPS | 不增加公开 Make 动作，不修改 lockfile 的隐式安装语义 |
| `ops/alerts/`、`ops/runbooks/`、部署调度配置 | 认证 SLI、告警、一次性清理调度、备份恢复和故障恢复手册 | 本地不运行常驻清理循环 |
| `infra/docker/` | 测试/生产同源 `/api` 反向代理、安全头和 API dispatcher 生命周期配置 | 不把业务服务加入 `compose.local.yml` |
| Gateway、Billing、Admin | 无功能变更 | 不新增认证存储、探针或认证业务行为 |

**Contracts**: 设计契约位于
[phone-auth-session.openapi.yaml](contracts/phone-auth-session.openapi.yaml)、
[business-codes.md](contracts/business-codes.md)、
[cookie-csrf.md](contracts/cookie-csrf.md) 和
[sms-delivery.md](contracts/sms-delivery.md)。实现时先将同一 v1 内容发布到
`shared/contracts/phone-auth-session/v1/`，再生成 Frontend TypeScript 类型并实现
双方消费者。公开路径为：

- `POST /api/v1/auth/verification-challenges`
- `POST /api/v1/auth/sessions`
- `GET /api/v1/auth/session`
- `DELETE /api/v1/auth/session`

既有统一 envelope 保持兼容；业务失败由稳定 `code` 表达，HTTP 状态、幂等键、
超时与重试语义、Cookie/CSRF 和反枚举投影均由上述 v1 契约固定。验证码投递遇到
timeout/unknown 不自动重发。`POST /verification-challenges` 在中性结果与 pending
challenge 提交后、dispatcher 调用 recipient-specific adapter 前返回 202；该响应不承诺
账户存在、短信已发送或实际送达。

**Data & Migrations**: [data-model.md](data-model.md) 定义
`verification_request_idempotency_records`、`verification_challenges`、
`auth_sessions`、`authentication_security_events`。迁移
`0003_phone_login_session` 只做 additive 变更；验证码核验、旧会话撤销和新会话
签发在一个短事务中完成，以 partial unique index 保证单 active session。请求幂等
事实与 dispatch state/lease 持久化在 PostgreSQL；dispatcher 先领取 pending work，
再在外部调用前持久化 send-started 事实，崩溃后只查询既有 `provider_request_ref` 或
作废，绝不自动重发。Redis Lua 原子执行手机号/IP 双 rolling 限流。常规回退停用新
入口但保留表和审计事实；破坏性 downgrade 需显式授权，并先在隔离 PostgreSQL 15
完成备份→恢复→认证不变量复核。

**Security & Privacy**: 原始 session token 仅存在于 `__Host-tokenmarket_session`
Cookie，数据库仅保存版本化 HMAC digest；OTP 由版本化 HMAC PRF 从随机 challenge id
通过 rejection sampling 无偏派生，dispatcher 只在进程内重算短信内容，数据库仍只保存
domain-separated 不可逆校验材料。所有 Cookie、`Set-Cookie`、CSRF、OTP、手机号、token
和密钥必须在日志/追踪中脱敏；手机号和 IP 只使用 keyed reference 聚合。可信代理 CIDR
显式配置并从链尾解析 `X-Forwarded-For`，不信任的直连 header 被忽略。状态变更请求
同时校验精确 Origin 和 session-bound CSRF token；公开挑战响应保持反枚举。依赖扫描、
secret scan、负向越权/重放/并发测试和浏览器 Cookie 检查是发布门禁。

隐私扫描使用每次运行唯一的 sentinel 值并区分“必要瞬时边界”与“禁止泄露面”。允许边界
仅有：用户正在编辑时手机号/OTP 输入控件自身的 value、服务端到目标浏览器的 wire-level
`Set-Cookie`、以及契约测试进程内的瞬时断言；这些值不得进入测试输出或 evidence。禁止面
包括响应正文、除 `Set-Cookie` 外的响应头、非输入控件 DOM、DOM attribute、可见调试区、
URL/history、Web Storage、BroadcastChannel、日志、异常、metric、trace、analytics、
snapshot、backup 和 evidence。提交后 OTP 必须清空；中性受理后 UI 只能保留脱敏手机号。
扫描必须证明 sentinel 在禁止面出现次数为零，同时单独验证 Cookie 属性及正文不复制凭证。

隐私验证按可实现 surface 分层：Foundation 只交付 sentinel 词表/allowlist 扫描器单元
测试，以及后端 HTTP、日志、异常、metric、trace 序列化边界；US1 增加输入 value 生命周期、
提交后 OTP 清空、响应正文和 Web Storage；US2 增加幂等键、raw phone、URL/history 与
中性 UI；US3 增加 Cookie/CSRF、BroadcastChannel 与多标签；P1 真实浏览器证据最后聚合
扫描全部禁止面。每层测试仍必须先于该层行为实现，不允许 Foundation 通过虚构尚未存在的
DOM、Web Storage 或 BroadcastChannel surface。

**Observability & Reliability**: 记录 request id、challenge/session reference、
结果码、阶段耗时和投递分类，不记录认证秘密或原始 PII；提供挑战请求、限流、核验
成功/失败、投递失败/unknown、会话签发/撤销、CSRF/Origin 拒绝、清理积压指标。告警
覆盖投递可用性、登录成功率、Redis/PostgreSQL 故障、撤销延迟和清理积压。Redis
不可用时验证码申请 fail closed；会话事实始终回源 PostgreSQL。dispatcher 暴露
pending/leased/dispatching/unknown age、claim 和 finalize 指标，并在优雅停止时停止
领取新 work、允许有界完成当前调用。API Service 一次性维护命令执行有界清理；测试和
生产由部署平台定时触发，本地仅手动执行，数据库 advisory lock 保证单一执行者，执行
失败、last-success 逾期和 backlog 告警均指向认证 runbook。

告警以 API Service authentication on-call 为 owner，用户字段错误、验证码错误和正常
限流不计入服务失败率。固定阈值如下：

| Signal | Warning | Critical |
|---|---|---|
| Auth readiness | — | 连续 5 分钟不可用 |
| Server/dependency failure ratio | 10 分钟 >5%，且至少 100 个 eligible 请求 | 5 分钟 >20%，且至少 50 个 eligible 请求 |
| Provider rejected/timeout/unknown ratio | 10 分钟 >10%，且至少 50 次 dispatch | 5 分钟 >25%，且至少 25 次 dispatch |
| Oldest eligible dispatcher work | >30 秒持续 5 分钟 | >120 秒持续 5 分钟 |
| Session revocation visibility p95 | — | 5 分钟 >1 秒，且至少 20 个样本 |
| Cleanup command | 单次失败或 last-success >2 小时 | 连续 3 次失败、last-success >4 小时或任一认证材料越过 24 小时硬期限 |
| Cleanup due backlog oldest age | >1 小时 | >2 小时 |

Warning 创建有 owner 的工作项并通知值班频道；Critical page on-call。恢复条件必须连续
两个评估窗口低于阈值，runbook 必须列明数据库、Redis、provider、dispatcher 和 cleanup
的分流诊断。

**Deployment & Rollback**: 发布顺序为契约与迁移 → 后端暗置且生产 fail closed →
同源 HTTPS/代理与 Frontend → 短信 adapter/TLS/key/可信代理配置验收 → 分阶段激活。
每一步运行契约、迁移、负向、并发、性能和浏览器 quickstart。部署清理调度必须与
API 镜像版本一起启用并验证 last-success；首次可部署门禁同时要求 US1、US2、US3。
回滚先关闭认证入口并回退应用镜像，保留 additive 数据表与安全事件；仅在隔离环境
备份恢复、认证不变量和 retry/head restoration 证据齐备后执行受保护的破坏性
downgrade。根 Makefile 仍是唯一公开工作流，CI YAML 继续只调用 `make ci`。

测试和生产以 UTC 每小时第 17 分钟调用一次性 cleanup；每次最多运行 15 分钟、每事务
最多处理 500 行，并由 advisory lock 保证单 owner。challenge/OTP material 的
`delete_after` 使用安全失效/过期后 22 小时，幂等记录使用创建后 22 小时，使一次小时级
调度延迟和 15 分钟运行预算后仍早于 24 小时硬期限。稳定逻辑入口固定为
`python -m app.maintenance.auth_cleanup --batch-size 500 --max-runtime-seconds 900`；
test/prod 调度在同版本 API Service 镜像中调用该入口，本地可从 API Service 的 locked
环境显式手动调用。不得复制第二套 cleanup wrapper、在 startup 启动循环或新增公开 Make
动作。

发布候选采用“源代码门禁 → 构建一次 → 绑定证据 → 真实部署预检”的不可变顺序。每个
P1/P2 候选先在冻结源代码上运行 `make ci`（包含格式、类型、lint、测试、安全、构建及
镜像门禁），随后生成 `evidence/candidate-p1.json` 或 `candidate-p2.json`，至少记录
increment、commit SHA、semantic version、source-tree clean 状态、全部应用 OCI image
digest、production frontend artifact/image digest、lock/contract hash 与 manifest
配套 `.sha256`。之后的 API 性能、浏览器、恢复、privacy 和 readiness evidence 必须引用
该 manifest SHA-256 与精确 digest；生成 manifest 后不得再格式化、修改源代码或重建。
任何源代码、lock、契约或 digest 变化均使既有 evidence 失效，必须从 `make ci` 重新开始。
candidate/evidence 可作为一个纯证据提交落库；此时 preflight 必须证明 candidate 的
source commit 到当前 HEAD 之间除 `specs/004-phone-login-session-ui/evidence/` 外没有
任何文件变化，部署对象仍是 manifest 中的原始 digest。

部署门禁分两层：`tests/workflow/test_auth_deploy_gate.py` 使用无 secret 的签名/合成
candidate 与 evidence fixture 验证 fail-closed 逻辑，不读取真实发布证据；真实
test/prod preflight 仅在 browser、performance、restore、cleanup/alert 和 traceability
证据全部生成后运行，并校验 manifest source commit 到当前 HEAD 的差异仅限 feature
`evidence/`、manifest hash 与将部署的 OCI/frontend digest 完全一致。最终验证只核验
绑定关系和 digest，不再次执行 `make build`。P2 若包含 US4
代码变化，必须生成新的 P2 candidate，并在其上重跑全部 P1 阻断证据；只有 P1/P2
candidate digest 完全相同时才可复用已绑定证据。

### P1 / P2 Release Gates

| Increment | Required scope | Blocking evidence | Explicitly not required |
|---|---|---|---|
| **P1 deployable authentication MVP** | Setup + Foundation + US1 + US2 + US3 | 四端点契约与生成漂移、迁移 forward/backout/retry、真实 PostgreSQL/Redis、反枚举/幂等/并发/CSRF/可信代理/脱敏、dispatcher crash recovery、session 恢复/替换/退出、authentication coverage ≥80%、固定 API 性能、P1 浏览器功能与性能、cleanup 调度和阈值告警、真实 backup→fresh restore、所有根 Make 门禁、`candidate-p1.json` digest 绑定、真实生产 readiness preflight | US4 的完整状态矩阵、320px/仅键盘完成率和 WCAG 2.2 AA 视觉验收 |
| **P2 complete authentication UI** | P1 全部通过 + US4 | 在 P2 candidate 上重跑全部 P1 阻断门禁；idle→unavailable 全状态、320px 无阻断、仅键盘完成率 100%、visible label/error/focus/aria 状态、WCAG 2.2 AA 对比度、刷新/多标签、P2 浏览器证据、`candidate-p2.json` digest 绑定与真实 readiness preflight | 完整设计系统、正式无障碍认证、国际化 |

P1 浏览器门禁必须在 production frontend build 上验证：不闪现受保护内容、Cookie/
CSRF 不可被脚本持久化、站内 redirect、刷新/退出闭环、验证结果到达后 1 秒内可感知、
20 次冷启动 p95≤3 秒、20 次完整旅程均≤3 分钟。上述性能与安全证据不得因 US4 为 P2
而延期。P2 对比度采用 WCAG 2.2 AA：普通文本至少 4.5:1，大号文本至少 3:1，交互控件、
状态边界和可见焦点指示器相对相邻颜色至少 3:1；disabled/inactive 例外必须在证据中
明确标识，不得被用来规避可操作控件要求。

## Constitution Check

*GATE：Phase 0 前已评估，并在 Phase 1 设计完成后复核。*

### Pre-Research Gate

| Gate | Result | Planned evidence |
|---|---|---|
| Architecture and ownership | PASS | API Service 独占认证事实；Frontend 只负责呈现；短信为 port；无跨服务数据访问 |
| Contracts and compatibility | PASS | 先定义 OpenAPI、业务码、Cookie/CSRF 与投递契约，再实现生产者和消费者 |
| Security and privacy | PASS | opaque Cookie、CSRF/Origin、HMAC、可信代理、反枚举、脱敏和 fail-closed 均有验证项 |
| Data correctness | PASS | PostgreSQL 事实源、dispatch lease/send-started、唯一约束、短事务、持久幂等、Redis Lua、保留、备份恢复和迁移策略明确 |
| Testing | PASS | 每项行为先有失败测试；单元、契约、真实依赖集成、负向、并发、≥80% coverage、可重复性能、备份恢复和浏览器验证均被规划 |
| Operations | PASS | dispatcher/清理调度、脱敏遥测、SLI、告警、降级、优雅停止和 runbook 范围明确 |
| Delivery | PASS | 依赖许可证/维护评审、固定工具链、lockfile、根 Make 门禁、分阶段发布和保数据回退明确 |
| Documentation language | PASS | 人工编写的 Spec/Plan/研究/设计/验证文档以简体中文为主，机器契约保留协议标识 |

当前实现中本地 HTTP、直接 API URL、宽泛 CORS、盲信最左侧 `X-Forwarded-For` 和
Cookie/CSRF header 脱敏缺口不是已接受的例外；它们是认证端点激活前必须完成并通过
负向测试的阻断任务。无 Constitution waiver。

### Post-Design Gate

| Gate | Result | Design evidence |
|---|---|---|
| Architecture and ownership | PASS | [research.md](research.md) Decisions 1、12；本计划 Affected Components |
| Contracts and compatibility | PASS | [contracts/](contracts/) 四份 v1 契约和 schema-checked client 决策 |
| Security and privacy | PASS | [cookie-csrf.md](contracts/cookie-csrf.md)、research Decisions 2、4、6—9、13 |
| Data correctness | PASS | [data-model.md](data-model.md) 的 dispatch lease、状态机、事务、保留、备份恢复和迁移 |
| Testing | PASS | [quickstart.md](quickstart.md) 与 research Decisions 17、19、20；fixture-first、分层隐私测试及 P1/P2 浏览器证据边界已锁定 |
| Operations | PASS | research Decisions 11、18；告警阈值、cleanup cadence、稳定 CLI 和 24 小时缓冲已锁定 |
| Delivery | PASS | quickstart 的根 Make 门禁、迁移矩阵、不可变 candidate 及真实部署预检 |
| Documentation language | PASS | Phase 0/1 人工文档均以简体中文为主 |

Phase 1 复核无失败项、无未解决 clarification、无复杂度例外。重新生成任务时必须先
建立并验证测试基础设施，再编写因缺失 schema/行为而失败的测试；部署代理、遥测、告警
和各故事隐私扫描测试仍位于对应实现前。告警任务必须逐字列出本计划表中的窗口、阈值、
最小样本量、severity、恢复两窗口和 owner，不得用“覆盖全部阈值”代替。P1 浏览器性能/
安全证据不得依赖 US4；P2 产生代码变化时先生成新 candidate，再在同一 digest 上重跑
P1 阻断证据和 US4 的完整状态、320px、键盘与 WCAG 2.2 AA。dispatcher、稳定 cleanup
CLI/调度、备份恢复、依赖治理、coverage、P1 性能和真实 deploy preflight 均为首次发布
阻断项。生产激活前的真实短信 adapter、TLS、密钥和可信代理配置缺失时由实现主动
fail closed，不构成架构豁免。

## Project Structure

### Documentation (this feature)

```text
specs/004-phone-login-session-ui/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── phone-auth-session.openapi.yaml
│   ├── business-codes.md
│   ├── cookie-csrf.md
│   └── sms-delivery.md
├── checklists/
│   └── requirements.md
├── evidence/
│   ├── candidate-p1.json
│   ├── candidate-p1.sha256
│   ├── candidate-p2.json
│   └── candidate-p2.sha256
└── tasks.md                             # 本轮计划后为 Stale，必须完整重建
```

### Source Code (repository root)

```text
services/api-service/
├── app/
│   ├── api/v1/auth.py                  # 扩展 challenge/session/bootstrap/logout
│   ├── domain/
│   │   ├── base.py                     # 共享 SQLAlchemy declarative base
│   │   ├── users/
│   │   └── authentication/             # challenge、session、事件状态与规则
│   ├── repositories/authentication.py
│   ├── schemas/authentication.py
│   ├── dispatch/auth_delivery.py       # 内部 durable dispatcher 生命周期
│   ├── security/
│   │   ├── csrf.py
│   │   ├── session.py
│   │   └── trusted_proxy.py
│   ├── sms/                            # provider-neutral port + synthetic adapter
│   ├── maintenance/auth_cleanup.py
│   ├── rate_limit.py
│   ├── dependencies.py
│   ├── observability.py
│   └── main.py
├── alembic/versions/
│   └── 0003_phone_login_session.py
└── tests/
    ├── unit/
    ├── contract/
    └── integration/

frontend/
├── src/
│   ├── api/
│   │   ├── client.ts
│   │   ├── generated/phoneAuth.ts      # 只生成类型，不手工编辑
│   │   └── v1/phoneAuth.ts             # 手写 facade，唯一消费 generated types
│   ├── auth/
│   │   ├── AuthContext.tsx
│   │   └── ProtectedRoute.tsx
│   ├── pages/
│   │   ├── Login.tsx
│   │   └── Dashboard.tsx
│   ├── layouts/AppShell.tsx
│   ├── types/auth.ts
│   ├── App.tsx
│   ├── styles/globals.css
│   └── **/*.test.ts(x)                 # 测试与被测模块共置
├── vite.config.ts
├── nginx.conf
├── .env.development.example
└── package-lock.json

shared/contracts/
├── phone-auth-session/v1/
└── user-registration/v1/               # 既有契约保持兼容

tools/workflow/
├── local_env/probes.py
├── local_stack/
├── release_candidate.py                # capture/verify，不新增公开 Make action
├── security.py
└── pyproject.toml

tests/workflow/
├── fixtures/auth-release/              # 无 secret 的合成 candidate/evidence
└── ...                                 # 工作流、依赖、恢复、部署门禁与脱敏回归测试

infra/docker/                            # 现有 test/prod 同源代理层
ops/
├── alerts/authentication.yml
├── schedules/authentication-cleanup.* # test/prod 平台一次性任务调度
└── runbooks/authentication.md

.env.example
Makefile
```

**Structure Decision**: 沿用既有 monorepo 边界：API Service 拥有认证领域和持久事实，
Frontend 只通过 v1 HTTP 契约消费；跨组件契约在 `shared/contracts/` 版本化。代理和
工作流只为同源 HTTPS 与就绪门禁做适配，不把认证逻辑下沉 Gateway，不新增独立 auth
service，也不将任何业务进程加入本地 Compose。

## Phase Outputs

| Phase | Artifact | Status |
|---|---|---|
| Phase 0 | [research.md](research.md) | Complete；20 个决策，所有研究问题均已解决 |
| Phase 1 | [data-model.md](data-model.md) | Complete |
| Phase 1 | [contracts/](contracts/) | Complete |
| Phase 1 | [quickstart.md](quickstart.md) | Complete |
| Phase 2 | [tasks.md](tasks.md) | Complete；已按 fixture-first、不可变 candidate、合成门禁/真实 preflight 分离、稳定 cleanup CLI 与分层隐私决策完整重建 |

## Agent Context

仓库没有 `.specify/scripts/bash/update-agent-context.sh` 或其他
`update-agent-context.*`，因此本阶段无法执行模板所述自动更新，且未补造未受仓库
治理的脚本。当前 feature pointer 已由 setup workflow 写入 `.specify/feature.json`
并指向 `specs/004-phone-login-session-ui`；后续实现代理应同时遵循根 `AGENTS.md`、
`.specify/memory/constitution.md`、本计划及同目录设计契约。

## Complexity Tracking

Constitution Check 无违规，不需要复杂度例外。

| Violation | Why Needed | Simpler Alternative Rejected | ADR / Owner | Controls | Review or Expiry |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Next Command

运行 `/speckit-analyze`，复核最新 `tasks.md` 的依赖顺序、需求覆盖、候选制品绑定与
P1/P2 门禁；高严重度问题清零后再进入 `/speckit-implement`。
