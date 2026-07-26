# Quickstart Validation：手机号验证登录、会话签发与基础界面

**Purpose**: 在真实 PostgreSQL 15、Redis 7 和浏览器入口上验证 SF04 的安全闭环。

**Contracts**: [contracts/](./contracts/)

**Data model**: [data-model.md](./data-model.md)

本文是实现后的验收指南，不包含完整实现代码。所有命令从仓库根目录执行。

## 1. Prerequisites

- `.tool-versions` 对应的 Go、Python/uv、Node/npm 与 Docker 可用。
- `.env.local` 已从 `.env.example` 创建并保持 gitignored。
- PostgreSQL/Redis 密码是独立生成的 `tm_local_...` synthetic secrets。
- 认证新增配置使用本机生成的 ignored secrets，至少包括：
  - versioned session-token HMAC current/previous keys；
  - versioned OTP HMAC current/previous keys；
  - versioned CSRF HMAC current/previous keys；
  - phone/IP/idempotency reference HMAC key；
  - trusted proxy CIDRs（本地只允许明确 loopback peer）；
  - exact origin `https://127.0.0.1:5173`；
  - local synthetic SMS adapter 与一个 6 位 synthetic code。

不得把真实手机号、真实短信密钥、raw OTP、Cookie 或上述 HMAC keys 写入命令历史、
截图、日志或本文件。

实现期首次编写迁移/集成测试前，必须先准确安装 locked testcontainers 依赖、注册
authentication pytest plugin，并以最小 smoke test 证明 PostgreSQL/Redis 容器、
可控时钟和 fake adapter fixture 可收集、可启动、可回收。之后的红灯必须到达断言并因
缺失 schema/行为失败；collection、import、fixture-not-found 或容器启动错误不算红灯。

## 2. Bootstrap, middleware, migration, and apps

```bash
make toolchain-check
make bootstrap
make dev
make migrate
make start scope=apps
```

Expected:

- PostgreSQL 15、Redis 7、Grafana 由 SF02 middleware lifecycle 管理；
- API、Gateway、Billing、Admin、Frontend 仍是五个 host processes；
- 浏览器入口为 `https://127.0.0.1:5173`，首次使用需接受本地自签名开发证书；
- `/api` 由 Vite HTTPS proxy 转发到 loopback API；
- API readiness 可确认数据库、auth key configuration 与 synthetic provider policy；
- migration head 包含 `0003_phone_login_session`，startup 没有自动建表。

若 auth key、trusted proxy、origin 或 provider 配置缺失，认证 readiness 必须失败关闭并给出
不含 secret 的诊断；不得回退到 insecure Cookie 或绕过限流。

## 3. Contract and static gates

```bash
make type-check
make lint
make test
make migrate-check
make migrate-integration-check
make security-check
```

Expected:

- OpenAPI 可解析，Frontend generated auth types 与
  `shared/contracts/phone-auth-session/v1/` 无 drift；
- Python auth domain 与 route coverage ≥80%，安全/并发分支有直接断言；
- 新增 `openapi-typescript`、`@vitejs/plugin-basic-ssl`、`testcontainers` 的准确 pin、
  lockfile、许可证、维护状态和传递依赖审查均有机器门禁与脱敏证据；
- 每项行为实现前均有至少一个相关自动化测试被记录为因功能缺失而失败，CSRF 直接
  负向测试先于 CSRF 实现；
- Vitest 覆盖 AuthProvider、ProtectedRoute、Login、AppShell 与 API client；
- PostgreSQL 15 migration upgrade/backout/retry/head restoration 通过；
- secret/dependency scan 不发现凭证、OTP、Cookie 或真实手机号。
- deploy-gate 自动化测试只读取 tests 下的无 secret 合成 candidate/evidence fixture；
  它验证缺项、hash/digest 不匹配和配置错误时 fail closed，不读取真实 P1/P2 evidence。

开发过程可重复运行上述门禁；一旦开始候选发布证据，必须遵循第 10 节的“构建一次”
顺序，不得在浏览器或恢复证据之后再运行会重建 artifact 的命令。


## 4. Prepare one synthetic active user

使用 SF03 注册页或注册契约创建一个 synthetic active 用户。注册成功页必须仍提示“尚未
登录”，并提供“去登录”入口；不得由注册流程自动签发 session。

示例 synthetic 手机号仅用于本地 ignored 数据：

```text
13800138000
```

## 5. Request challenge and prove idempotency

为 curl 使用临时目录，避免把 Cookie jar 放入仓库：

```bash
AUTH_QS_TMP="$(mktemp -d)"
AUTH_BASE="https://127.0.0.1:5173"
AUTH_ORIGIN="https://127.0.0.1:5173"
```

第一次请求：

```bash
curl -k -sS -D "$AUTH_QS_TMP/challenge.headers" \
  -H "Origin: $AUTH_ORIGIN" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: qs-challenge-1" \
  -H "Idempotency-Key: qs-active-001" \
  -d '{"phone":"13800138000"}' \
  "$AUTH_BASE/api/v1/auth/verification-challenges"
```

Expected HTTP 202、`code="0"`，并返回：

- opaque `challenge_id`；
- masked phone；
- absolute `expires_at` 与 `resend_available_at`；
- 无 OTP、账户状态或 delivery receipt。

自动化契约/集成测试使用可阻塞 fake adapter：保持 adapter 未释放时，HTTP 请求仍须在
500ms 目标内返回 202；随后释放 dispatcher 才允许形成内部 accepted/rejected/timeout
结果。这证明请求线程没有等待 recipient-specific provider。

在 60 秒内以同 key/phone 重放，响应必须恢复相同 `challenge_id`，provider call、challenge
row 和 Redis attempt 均不增加。相同 key 改成另一个合法手机号必须返回
`IDEMPOTENCY_KEY_CONFLICT` 且无投递。

把返回值中的 UUID 记为 `<challenge_id>`；不要从数据库读取验证码明文（数据库中不存在
明文）。

## 6. Verify leading-zero OTP and inspect Cookie

使用 `.env.local` 中的 synthetic 6 位 code（本例用 `<synthetic-code>` 占位）：

```bash
curl -k -sS -D "$AUTH_QS_TMP/session-a.headers" \
  -c "$AUTH_QS_TMP/jar-a.txt" \
  -H "Origin: $AUTH_ORIGIN" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: qs-session-a" \
  -d '{"challenge_id":"<challenge_id>","code":"<synthetic-code>"}' \
  "$AUTH_BASE/api/v1/auth/sessions"
```

Expected:

- HTTP 200、`code="0"`；
- body 仅有用户摘要、expiry、CSRF token；没有 session credential；
- Set-Cookie 为 `__Host-tokenmarket_session`，含 `Secure`、`HttpOnly`、
  `SameSite=Lax`、`Path=/`、`Max-Age=3600` 且无 Domain；
- `Cache-Control: no-store`。

分别用配置为 `000000`、`012345`、`999999` 的 synthetic test fixture 运行自动化边界用例；
leading zero 必须保留。全角、空白、5/7 位、字母/符号输入返回 `VALIDATION_ERROR` 且
attempt count 不增加。

## 7. Bootstrap, CSRF, and current session

```bash
curl -k -sS \
  -b "$AUTH_QS_TMP/jar-a.txt" \
  -H "X-Request-ID: qs-bootstrap-a" \
  "$AUTH_BASE/api/v1/auth/session"
```

Expected HTTP 200，返回 masked identity、role、expiry 与 session-bound `csrf_token`。把
它临时记为 `<csrf-a>`；不得写入仓库文件或浏览器持久存储。

Negative checks:

- 无 Cookie → `UNAUTHENTICATED`；
- 伪造/截断 Cookie → `UNAUTHENTICATED` 且清 Cookie；
- wrong/missing Origin 或 CSRF 的 authenticated DELETE → 403、session 仍有效；
- 响应与日志不出现 Cookie/CSRF 原值。

## 8. Prove one active session with two cookie jars

为同一用户再请求一个新 challenge 并在 jar B 中登录。使用新的 idempotency key 和
`jar-b.txt`。B 登录成功后 1 秒内：

```bash
curl -k -sS -o /dev/null -w '%{http_code}\n' \
  -b "$AUTH_QS_TMP/jar-a.txt" \
  "$AUTH_BASE/api/v1/auth/session"

curl -k -sS -o /dev/null -w '%{http_code}\n' \
  -b "$AUTH_QS_TMP/jar-b.txt" \
  "$AUTH_BASE/api/v1/auth/session"
```

Expected:

- jar A → 401；
- jar B → 200；
- PostgreSQL 最终只有一个该用户 `revoked_at IS NULL` session；
- 旧设备 logout 不能撤销 jar B。

100 次并发双登录与同 challenge 验证由自动化 integration tests 执行，必须检查最终
PostgreSQL 不变量，而不只检查 HTTP。

## 9. Idempotent logout

先用 jar B bootstrap 获得 `<csrf-b>`，再执行：

```bash
curl -k -sS -X DELETE \
  -b "$AUTH_QS_TMP/jar-b.txt" \
  -c "$AUTH_QS_TMP/jar-b.txt" \
  -H "Origin: $AUTH_ORIGIN" \
  -H "X-CSRF-Token: <csrf-b>" \
  -H "X-Request-ID: qs-logout-b" \
  "$AUTH_BASE/api/v1/auth/session"
```

Expected HTTP 200、`logged_out=true`，并以相同 Cookie scope 清除凭证。重复 logout 仍
安全成功；随后 GET session 为 401。数据库/网络结果不确定时，客户端先 bootstrap
确认，不得在依赖不可用时假称退出成功。

## 10. Browser user journey

### Freeze one release candidate before collecting evidence

P1 完成 US1—US3、P2 完成 US4 后，先确认工作树清洁并运行一次完整源代码/构建门禁：

```bash
git status --short
make ci
uv run --project tools/workflow --locked workflow release-candidate capture \
  --increment p1 \
  --output specs/004-phone-login-session-ui/evidence/candidate-p1.json
```

P2 将 `p1`/`candidate-p1.json` 替换为 `p2`/`candidate-p2.json`。capture 必须拒绝 dirty
tree，并记录 commit SHA、semantic version、全部应用 OCI image digest、production
frontend artifact/image digest 与 lock/contract hash；manifest SHA-256 写入同 basename
的 `.sha256` companion，避免 JSON 自引用。capture 后不得运行 formatter、修改
source/contract/lock 或重建；任何变化都使本轮 evidence 失效，需从 `make ci` 重新开始。

candidate 与 evidence 可最后形成一个纯证据提交；verify 必须证明 manifest 的 source
commit 到当前 HEAD 之间仅 `specs/004-phone-login-session-ui/evidence/` 有变化，否则
整轮证据失效。

以下 curl、API 性能、真实浏览器、privacy、backup/restore、cleanup/alert 与
traceability evidence 都必须写入对应 candidate manifest SHA-256 和实际 digest。
本节前面的开发期手工验证不算发布证据，除非是在该候选上重新执行并完成绑定。

在真实浏览器执行：

1. 未登录访问 `/dashboard`；
2. ProtectedRoute 显示 checking，不闪现受保护内容，随后进入 `/login`；
3. 输入 synthetic phone，发送后焦点进入 OTP；
4. 刷新页面，challenge masked metadata 与绝对倒计时恢复；
5. 输入 leading-zero code 登录，返回原 `/dashboard`；
6. 刷新仍恢复 authenticated state；
7. AppShell 显示 masked identity、role、dashboard、logout，隐藏重复 login；
8. 打开第二标签后登录/退出，另一标签通过无敏感 BroadcastChannel event 重新 bootstrap；
9. logout 后受保护内容不可见。

### P1 browser release evidence

P1 在 `candidate-p1.json` 绑定的同一 production frontend build 上必须证明：

- checking 期间不闪现受保护内容，redirect 仅恢复站内目标；
- JavaScript 不可读取 session Cookie，CSRF、OTP 和 raw phone 不进入 Web Storage 或
  BroadcastChannel；
- 使用同一 commit 的 production frontend build、无 CPU/network throttling、至少
  4 vCPU/8 GiB 验收设备；记录 OS、CPU、内存、浏览器准确版本、commit、candidate
  manifest SHA-256 与 frontend digest；
- 清缓存冷启动 20 次并从 navigation start 到主登录表单可操作标记计时，p95 ≤3 秒；
- 完整“入口→请求→验证→Dashboard→刷新→退出”合成旅程执行 20 次，每次 ≤3 分钟；
- UI fake-timer 自动化测试证明验证码验证响应到达后 1 秒内进入可感知结果状态。

### P2 complete UI evidence

P2 必须在 `candidate-p2.json` 绑定的 artifact 上追加，并在该 artifact 上重跑所有 P1
阻断证据；只有 P1/P2 manifest 记录的全部 digest 完全相同时才可复用既有 P1 evidence：

- 仅键盘完成发送、输入、登录、退出，完成率 100%；
- visible labels、error association、focus correction、busy/status 可感知；
- 倒计时不每秒骚扰读屏；
- 320px viewport 无横向滚动阻断；
- WCAG 2.2 AA：普通文本 ≥4.5:1，大号文本 ≥3:1，交互控件、状态边界和可见焦点
  指示器相对相邻颜色 ≥3:1；disabled/inactive 例外逐项记录。

### Privacy sentinel scan boundary

每次验收生成唯一 raw phone、OTP、Cookie、CSRF、idempotency key 和 HMAC key sentinel。
用户正在编辑时，仅手机号/OTP 输入控件自身 value 可以出现对应输入 sentinel；
wire-level `Set-Cookie` 仅允许在发往目标浏览器的响应头中出现，契约测试只可在进程内
瞬时断言且不得输出。提交后 OTP 清空，中性受理后只显示 `phone_masked`。

对响应正文、其他响应头、非输入控件 DOM、DOM attributes、URL/history、Web Storage、
BroadcastChannel、日志、异常、metric、trace、analytics、snapshot、backup 和 evidence
执行扫描，sentinel 命中数必须为零。Cookie 属性测试与泄露扫描分开：前者证明安全交付，
后者证明凭证未被复制或持久化。

扫描逐层启用：Foundation 仅覆盖 scanner/allowlist 与后端 HTTP/log/error/metric/trace；
US1 加入输入 value、OTP 清空、response body/Web Storage；US2 加入 idempotency/raw
phone 的 URL/history/storage 和中性 UI；US3 加入 Cookie/CSRF/BroadcastChannel；
本节真实浏览器证据聚合全部禁止面。不得要求 Foundation 通过尚未实现的 DOM 或多标签
surface。

不得删除离群值或只保留成功样本。原始证据只含时间、版本和资源摘要，不含手机号、
OTP、Cookie、CSRF 或 key。

## 11. Failure, abuse, and recovery matrix

自动化或受控测试必须证明：

- active/unknown/suspended/deleted challenge 响应 code/status/message/shape 一致；
- 在固定 API 档案（至少 4 vCPU/8 GiB、PostgreSQL 15.18、Redis 7.2、host API、
  synthetic adapter、5 次预热）下，每类各 100 次 challenge request 的 p95 ≤500ms，
  任意两类 p95 差值 ≤100ms，并记录 p50/p95/max；
- 第 5 次错误 code 锁定，旧/expired/superseded/replayed code 建立 session 数为 0；
- 同 idempotency winner 100 并发 → 1 adapter call、1 challenge、1 rate-limit count；
- phone 第 6 次/小时、trusted IP 第 21 次/小时统一 `RATE_LIMITED`；
- 伪造 XFF 无法切换 bucket，可信代理链从右向左解析；
- Redis down：新 challenge 503；已有 session 仍由 PostgreSQL 校验；
- DB down：protected request 503/fail-closed，不返回受保护数据；
- provider fake 被阻塞时 HTTP 202 已返回；dispatcher lease 并发领取只有一个 winner；
- dispatcher 在 `send_started_at` 前崩溃可恢复领取，之后崩溃只能 query-or-invalidate，
  provider timeout/restart 不自动 resend、不留下 usable challenge；
- production + synthetic/missing provider/key/TLS facts：auth readiness fail-closed；
- test/prod 部署调度在同版本 API Service 镜像中调用以下稳定的一次性逻辑入口，本地从
  API Service locked 环境手动执行相同入口，不新增公开 Make action：

```bash
uv run --project services/api-service --locked \
  python -m app.maintenance.auth_cleanup \
  --batch-size 500 \
  --max-runtime-seconds 900
```

- 并发 cleanup 触发由 advisory lock 保证单 owner，
  UTC 每小时第 17 分钟触发，每次 ≤15 分钟、每事务每表 ≤500 行；重复运行安全，本地无
  常驻清理循环；
- challenge/OTP 的 `delete_after = expires_at + 22h`、幂等记录的
  `delete_after = created_at + 22h`；受控时钟证明最坏调度与运行预算仍早于 24 小时；
- auth readiness 连续 5 分钟不可用触发 Critical；
- 服务/依赖失败率 10 分钟 >5% 且 ≥100 eligible 请求触发 Warning，5 分钟 >20% 且
  ≥50 请求触发 Critical；
- provider rejected/timeout/unknown 比率 10 分钟 >10% 且 ≥50 dispatch 触发 Warning，
  5 分钟 >25% 且 ≥25 dispatch 触发 Critical；
- 最老 eligible work >30 秒持续 5 分钟触发 Warning，>120 秒持续 5 分钟触发 Critical；
- session revocation visibility p95 在 5 分钟内 >1 秒且 ≥20 样本触发 Critical；
- cleanup 单次失败或 last-success >2h 触发 Warning；连续 3 次失败、last-success >4h
  或任一认证材料越过 24h 触发 Critical；due backlog >1h / >2h 分别 Warning/Critical；
- 按第 10 节 sentinel allowlist 扫描，所有禁止面命中数为零。

## 12. Migration rollback evidence

在隔离 PostgreSQL 15 中验证：

```text
0002 head
  → upgrade 0003
  → exercise auth tables/constraints
  → downgrade 0002
  → retry upgrade 0003
  → restore repository head
```

正常应用回滚只回退 API/Frontend image，保留 additive `0003` 表。破坏性 downgrade 前
必须停 auth 流量、撤销 session 并完成 90/180 天数据保留决策。

## 13. Backup and restore evidence

迁移 `restore repository head` 只证明 schema 序列，不算数据恢复。使用隔离
PostgreSQL 15：

1. 创建包含 pending/dispatching/delivered/consumed challenge、active/revoked session
   和安全事件的 synthetic 数据集；
2. 生成真实数据库备份及只含表名、行数、opaque reference 的脱敏 manifest；
3. 恢复到全新数据库；
4. 验证 consumed challenge 不可用、revoked session 不恢复、每用户最多一个 active
   session，且 `send_started_at` work 不会再次 send；
5. 运行认证契约、并发和 retention 校验，保存脱敏恢复证据。

恢复证据必须记录镜像 digest、工具版本、commit、开始/完成时间和结果；不得包含数据库
secret、完整手机号、OTP、Cookie、CSRF 或 HMAC key。

## 14. Verify bound evidence and run the real deploy preflight

只有 browser、performance、privacy、backup/restore、cleanup/alert、quality-gate 和
traceability evidence 全部存在后，才运行真实门禁：

```bash
uv run --project tools/workflow --locked workflow release-candidate verify \
  --manifest specs/004-phone-login-session-ui/evidence/candidate-p1.json

make deploy mode=test \
  auth_release_manifest=specs/004-phone-login-session-ui/evidence/candidate-p1.json
```

P2 使用 `candidate-p2.json`。verify/preflight 必须检查 manifest source commit 到当前
HEAD 的差异仅限 evidence 目录、manifest SHA-256、全部 evidence 绑定和实际将部署
digest；缺一项、hash 不符、source/lock/contract 有 evidence 外变化或环境仍为 synthetic
都 fail closed。此阶段禁止重新执行 `make build` 或 `make ci`。生产部署沿用同一
manifest 与已审查 evidence，通过既有 `make deploy mode=prod` 流程显式执行。

## 15. Stop and cleanup

```bash
make stop
```

`make stop` 保留 PostgreSQL/Redis named volumes。临时 Cookie jar 属于本机敏感测试材料，
验收结束后删除整个 `AUTH_QS_TMP` 明确目录；不得提交或附在 issue/PR。
