# Quickstart Validation：角色授权与自买自卖隔离

**Purpose**: 在真实 PostgreSQL 15（及可选 Redis）上验证 SF05 角色矩阵、所有权、
自买自卖排除、统一 404 与可恢复授权审计。

**Contracts**: [contracts/](./contracts/)  
**Data model**: [data-model.md](./data-model.md)  
**Research**: [research.md](./research.md)

本文是实现后的验收指南，不包含完整实现代码。命令默认从仓库根目录执行。

## 1. Prerequisites

- `.tool-versions` 对应的 Go、Python/uv、Node/npm 与 Docker 可用。
- SF03 注册与 SF04 登录会话在当前 `master-dev` 基线上可用（本功能依赖会话与
  `users` 角色/状态）。
- `.env.local` 已从 `.env.example` 创建并保持 gitignored。
- 本地启用夹具（**仅 local/test**）：

```bash
# .env.local（示例名，以实现为准）
AUTHORIZATION_FIXTURES_ENABLED=true
APP_ENV=local
```

生产或未显式开启时夹具路由必须不可用（404 或未挂载），不得依赖前端。

不得把真实手机号、会话 Cookie、HMAC keys、原始 Key 写入命令历史、截图、日志或本文件。

## 2. Bootstrap, middleware, migration, apps

```bash
make toolchain-check
make bootstrap
make dev
make migrate
make start scope=apps
```

Expected:

- PostgreSQL 15、Redis 7、Grafana 由 SF02 lifecycle 管理；
- 迁移 head 包含 `0004_role_access_isolation`（或实现命名的等价 head）；
- 存在表 `resource_ownerships`、`authorization_security_events`、
  `authorization_audit_outbox`（若采用 outbox）；
- API readiness 在授权依赖（DB）不可用时 fail-closed；
- 启动未自动建表。

## 3. Contract and static gates

```bash
make type-check
make lint
make test
make migrate-check
make security-check
```

Expected:

- OpenAPI 可解析；实现后与 `shared/contracts/role-access-isolation/v1/` 无契约漂移；
- `authorization` 域与路由行覆盖 ≥80%；拒绝、自买自卖、失败关闭有直接断言；
- 矩阵表驱动测试覆盖全部 `buyer|seller|both` × 声明动作；
- secret/dependency scan 无凭证泄漏。

## 4. Seed three roles (synthetic)

使用合成手机号注册并登录三类账户：`buyer`、`seller`、`both`（走既有 SF03/SF04 流程）。
保存各自会话 Cookie 于环境变量（勿入库、勿提交）：

```bash
# 示意：COOKIE_BUYER / COOKIE_SELLER / COOKIE_BOTH
```

## 5. Matrix smoke (HTTP fixtures + evaluate)

### 5.1 buyer 允许代理 Key，拒绝卖家 Key

```bash
# buyer: create proxy ownership — expect 200 code=0
curl -sk -b "$COOKIE_BUYER" -H 'Content-Type: application/json' \
  -H "X-Request-ID: qs-buyer-proxy-create" \
  -d '{"resource_type":"proxy_key","action":"proxy_key.create"}' \
  https://127.0.0.1:5173/api/v1/authorization/fixtures/resources

# buyer: seller register — expect 403 FORBIDDEN_ROLE
curl -sk -b "$COOKIE_BUYER" -H 'Content-Type: application/json' \
  -H "X-Request-ID: qs-buyer-seller-register" \
  -d '{"resource_type":"seller_key","action":"seller_key.register"}' \
  https://127.0.0.1:5173/api/v1/authorization/fixtures/resources
```

### 5.2 seller 对称

- `seller_key.register` → 200  
- `proxy_key.create` → 403 `FORBIDDEN_ROLE`

### 5.3 both 两类均可，但仍受所有权约束

- both 可创建 proxy 与 seller 资源各一；
- 使用 **buyer Cookie** 读取 both 的 seller `resource_id` → **404** `RESOURCE_NOT_FOUND`  
  （与随机不存在 UUID 同码）；
- body 携带他人 `user_id` 不得抬权。

### 5.4 自买自卖排除

构造候选：一条 `owner_user_id=both` 的 seller_key，一条他人 active seller_key。

```bash
curl -sk -b "$COOKIE_BOTH" -H 'Content-Type: application/json' \
  -H "X-Request-ID: qs-self-route" \
  -d '{"candidates":[...]}' \
  https://127.0.0.1:5173/api/v1/authorization/route-candidates/exclude-self
```

Expected:

- 响应候选不含本人 `owner_user_id`；
- 仅本人候选时 → 404 `NO_ROUTE_CANDIDATE`，绝不回填本人 Key。

## 6. Account status and session identity

- 将用户 `status` 置为 suspended（测试仓储/夹具）后，任意 evaluate → 403
  `ACCOUNT_UNAVAILABLE`；
- 无 Cookie → 401 `UNAUTHENTICATED`；
- **登出或撤销会话后**再 evaluate → 401 `UNAUTHENTICATED`，允许次数为 0（SC-006）；
- 会话仍有效但 DB 角色从 both 改为 buyer 后，立即（≤1s）拒绝 seller 动作。

## 7. Audit

- 触发一次 `FORBIDDEN_ROLE` 与一次跨用户 404；
- 用 `request_id` 在 `authorization_security_events`（或 outbox 刷写完成后）查到
  脱敏事件：含 `action`、`reason_code`、`policy_version`，无密钥；
- 高频 `proxy_key.use` 允许路径不新增逐条授权审计，指标可增。

审计顺序（FR-010a）：

1. 正常路径：先落盘 event/pending → 再收到业务 403/404；  
2. 模拟落盘失败：必须 **503** `SERVICE_UNAVAILABLE`，**不得**返回无证据的 403/404。

## 8. Fail-closed

- 停止 PostgreSQL 或断开 API DB 配置后，evaluate/fixtures → 503
  `SERVICE_UNAVAILABLE`，无 allow。

## 9. Automated acceptance map

| Spec criterion | How to prove |
|----------------|--------------|
| SC-001 矩阵 100% | 表驱动单元 + 夹具集成 |
| SC-002 自排除 0 命中 | 1000 次候选生成属性/循环测试 |
| SC-003 1s 生效 | 角色/所有权变更后立即请求 |
| SC-004a 直读 P95 | 可选微基准 / 记录环境 |
| SC-004b 加速命中 P95 | 仅当启用加速时 |
| SC-004c 无 fail-open | 断 DB；可选断缓存 |
| SC-005 强制审计可查 | request_id 查询；意图失败 → 503 非裸 403 |
| SC-006 会话撤销 | 撤销后 evaluate → 401 |

## 10. Production checklist

- [ ] `AUTHORIZATION_FIXTURES_ENABLED` 在 prod 为 false 或未设置  
- [ ] 夹具路由未暴露或统一 404  
- [ ] 契约已提升至 `shared/contracts/role-access-isolation/v1/`  
- [ ] 迁移已在隔离环境 forward/backout 验证  
- [ ] 告警：授权 503 率、审计 outbox 积压（若启用 worker）  
