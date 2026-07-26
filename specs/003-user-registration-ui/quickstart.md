# 快速验收：用户注册与初始界面

**特性**: `003-user-registration-ui`
**目的**: 实施后的验收指南；并发、迁移与限流边界仍以自动化测试为准
**安全**: 仅使用合成手机号与本地凭据。切勿指向开发工作区以外的测试/生产数据存储。

## 0. 前置条件

- 已检出特性分支 `003-user-registration-ui`。
- 工具链：Go/Python/Node 版本按仓库 pin。
- 本地 PostgreSQL 与 Redis 可用（SF02 `make dev` 已激活时，或 CI 夹具所用的等价隔离测试容器）。
- API Service 的 `DATABASE_URL` 与 Redis URL **仅**配置为本地。
- 契约可读于 [contracts/](./contracts/)。

## 1. 质量门禁（仓库）

在仓库根目录：

```bash
make lint
make test
```

预期：

- API 用户域包满足覆盖率策略（变更域代码 ≥80%）。
- Frontend 类型检查、lint 与 Vitest 通过。
- `user-registration/v1` 提升后无契约资产校验失败。

## 2. Schema 迁移

```bash
cd services/api-service
# apply reviewed revision that creates users + registration_idempotency_records
make migrate   # or project-standard alembic upgrade head via root make migrate
```

预期：

- 在 baseline 之后的空库上 upgrade 成功。
- Downgrade 路径可无错移除新表/类型（仅在可丢弃库上执行）。

## 3. API 成功路径

按服务 README 启动 API Service（主机进程）。然后：

```bash
REQ=req-$(uuidgen)
KEY=idem-$(uuidgen)
curl -sS -X POST "http://127.0.0.1:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -H "X-Request-ID: $REQ" \
  -d '{"phone":"+86 138 0013 8000","nickname":"验收用户","role":"buyer"}'
```

预期：

- HTTP 200，`code` = `"0"`。
- `data.user_id` 为 UUID，`data.role` = `buyer`，`data.status` = `active`，含 `created_at`。
- 响应体无完整手机号；仅可选 `phone_masked`。
- 响应与日志含 `request_id`；日志不得出现完整 `13800138000`。

使用相同键与请求体重放 → 同一 `user_id`，DB 仍仅一行。

## 4. API 负向用例（手工或测试套件）

| 用例 | 预期 |
|------|------|
| 第二次注册、新键、同号 | `PHONE_ALREADY_REGISTERED`，HTTP 409，仍仅一用户 |
| 软删除用户同号（夹具） | `ACCOUNT_UNAVAILABLE`，与占用语义可区分 |
| 非法手机号 / 昵称 / 角色 | `VALIDATION_ERROR` 含字段错误 |
| 同键、不同昵称 | `IDEMPOTENCY_KEY_CONFLICT` |
| 过期键（>24h；测试中用时钟夹具） | `IDEMPOTENCY_KEY_EXPIRED` |
| 15 分钟内突发 >20/IP 或 >5/手机号 | `RATE_LIMITED`，HTTP 429，无新用户 |
| DB 宕机 | `SERVICE_UNAVAILABLE` / 503，无部分用户 |
| Redis 宕机 | 注册 503 fail-closed（禁止无限写入） |

## 5. 并发抽查

优先自动化测试：100 个并行 POST、同一规范化手机号、不同键 → 恰好一条 `users` 行；其余冲突/限流。

## 6. 前端壳层

```bash
cd frontend
make bootstrap   # if required
npm run dev
```

浏览器检查：

1. 打开 `/` → 首页 **占位** 壳层，**不是** 注册表单；可见注册导航链接。
2. **首屏可交互（ER-004）**: 常规冷启动 `npm run dev` 后，在典型开发机打开 `/register`；**3 秒内** 手机号/昵称/角色字段与提交控件应可操作（可聚焦/可输入）。在笔记中记录通过/失败——此为 **手工** 验收，非 CI 门禁。
3. 打开 `/register` → 手机号、昵称、角色、提交。
4. 提交合法合成手机号 → 成功确认含用户 id + 角色；文案说明 **尚未登录**。
5. 提交非法字段 → 字段级错误。
6. 提交重复手机号 → 中性占用提示（无其他账户 PII）。
7. 打开未知路径 → 未找到/占位，含回首页或注册链接。
8. 仅键盘可完成表单。

自动化：`npm test` 覆盖路由渲染与主要表单状态。

## 7. 本地端到端路径（SC-006）

API + frontend + DB + Redis 均已启动：

1. 从 `/` 经 UI 导航到注册。
2. 在 2 分钟内完成注册。
3. 确认成功 UI 与单条 DB 行。

## 8. 隐私扫描

```bash
# example: scan recent API logs / test artifacts for raw fixture phones
# must find only masked forms or no match
```

若注册日志字段或错误体中出现完整手机号模式，CI/安全测试应失败。

## 9. 回滚演练（非生产）

1. 停止接受注册流量。
2. 部署上一版 API 镜像 **或** 禁用路由。
3. 仅在可丢弃库上：`alembic downgrade` 一个修订；确认表已移除。
4. Frontend 回滚为独立静态资源回退。

## 可追溯性（规格 → 证据）

| 成功标准 | 主要证据 |
|----------|----------|
| SC-001 / SC-002 | 集成 + 并发测试 |
| SC-003 | 幂等单元/集成 + 过期夹具 |
| SC-004 | 计时断言或集成负载微基准 |
| SC-005 | 日志/响应脱敏测试 |
| SC-006 | 手工 quickstart §7 或 e2e 脚本 |
| SC-007 | API + UI 错误映射测试 |
| SC-008 | 前端路由测试 |
| SC-009 | 限流集成测试 |
