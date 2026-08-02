# Quickstart Validation：火山方舟凭证与额度验证

**Purpose**: 在本地网关进程内用 **受控 HTTP 替身**（非真实火山）验证 SF06 分类、
超时/取消、并发闸门与防泄漏。

**Contracts**: [contracts/](./contracts/)  
**Data model**: [data-model.md](./data-model.md)  
**Research**: [research.md](./research.md)

本文是实现后的验收指南，不含完整实现代码。命令默认从仓库根目录执行。

## 1. Prerequisites

- `.tool-versions` 中的 Go 1.25.x 可用。
- 本功能 **不依赖** PostgreSQL 业务表；SF02 中间件可选（仅当整仓 `make start`）。
- **禁止** 将真实火山 API Key 写入仓库、夹具、本文件或 CI 日志。
- 内部路由默认关闭；验收时在 **local/test** 开启：

```bash
# .env.local（示例名，以实现为准；必须 gitignored）
APP_ENV=local
PROVIDER_VALIDATE_INTERNAL_ENABLED=true
PROVIDER_VALIDATE_INTERNAL_TOKEN=local-dev-only-token
PROVIDER_VALIDATE_BIND=127.0.0.1
PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK=false
VOLCANO_VALIDATE_BASE_URL=http://127.0.0.1:18080/api/v3
VOLCANO_V01_CHAT_MODELS=doubao-pro-32k,doubao-lite-32k
VOLCANO_VALIDATE_GLOBAL_CONCURRENCY=32
VOLCANO_VALIDATE_PER_CREDENTIAL_CONCURRENCY=1
VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS=5
VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS=300
```

`VOLCANO_VALIDATE_BASE_URL` 指向测试替身，**不是**生产方舟地址。  
test/prod **不得**仅靠静态 token 对公网暴露内部路由（见 plan Security / research D9）。

## 2. Bootstrap and unit/contract tests

```bash
make toolchain-check
make bootstrap
cd services/proxy-gateway && make test
# 或根：make test（过滤 gateway 包，以实现 Makefile 为准）
```

Expected:

- domain 分类器表驱动覆盖全部 `error_category`；
- `quota_unavailable` 路径 `remaining_quota` 不为 `"0"`；
- `rate_limited` 无 `Retry-After` 时 `retry_after_seconds=5`；
- 日志/错误 helper 单测扫描无完整 Key；
- 相关包行覆盖 ≥80%。

## 3. Start gateway with mock upstream（实现提供）

实现应提供可启动的 mock（测试内 `httptest.Server` 或 `make` 目标）。示意：

```bash
# 终端 A：mock 上游（返回 models 金标）
# 终端 B：
export PROVIDER_VALIDATE_INTERNAL_ENABLED=true
export PROVIDER_VALIDATE_INTERNAL_TOKEN=local-dev-only-token
export VOLCANO_VALIDATE_BASE_URL=http://127.0.0.1:18080/api/v3
# 启动 gateway 主机进程（make start scope 或 gateway 专用目标）
```

## 4. Internal validate smoke

```bash
curl -sS -X POST "http://127.0.0.1:8080/internal/v1/provider-credentials/validate" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: local-dev-only-token" \
  -H "X-Request-Id: qs-sf06-1" \
  -d '{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real"}'
```

### 4.1 V0.1 默认（无额度 API）期望

- HTTP 200（业务结果在 body）  
- `error_category` = `quota_unavailable`  
- `remaining_quota` 为 `null` 或不存在  
- `supported_models` 为数组（可能已计算或为空，以实现流水线为准；不得伪造额度）  
- 响应 JSON **不含** 完整 `api_key`

### 4.1a 非 volcano 平台（I1）

```bash
curl -sS -X POST "http://127.0.0.1:8080/internal/v1/provider-credentials/validate" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: local-dev-only-token" \
  -d '{"platform":"openai","api_key":"sk-synthetic-test-key-not-real"}'
```

期望：HTTP **200**（非 422），`error_category` = `unsupported_platform`。

### 4.2 Mock：401

- `error_category` = `invalid`，`validity` = `invalid`

### 4.3 Mock：429 无 Retry-After

- `error_category` = `rate_limited`  
- `retry_after_seconds` = `5`

### 4.4 Mock：200 + 可信额度替身 >0 + 模型交集非空

- 通过测试注入 `QuotaReader` 替身（非默认 Noop）  
- `error_category` = `success`，`availability` = `available`，`remaining_quota` 精确匹配

### 4.5 并发闸门

- 同 Key 第二路并发 → `temporary_unavailable`，mock 上游调用计数不增加  
- 全局第 33 路（默认 32）同理  

### 4.6 取消

- 客户端在 100ms 取消 → 迅速返回；无连接泄漏（测试断言）

## 5. Negative：token 与开关

```bash
# 错误 token → 401
# PROVIDER_VALIDATE_INTERNAL_ENABLED=false → 404 或未挂载
```

## 6. Static gates

```bash
make lint
make type-check
make test
make security-check
```

Expected：无真实 Key 入仓；OpenAPI 与实现字段一致（实现后提升到
`shared/contracts/volcano-key-validation/v1/`）。

## 7. Out of scope for this quickstart

- 真实火山集成（可选 `VOLCANO_LIVE_SMOKE=1` 人工，不入默认 CI）  
- SF08 持久化接入、SF16 调度  
- 多平台  

## 8. Traceability

| Spec | Quickstart step |
|------|-----------------|
| SC-001 / 分类 | §2, §4.2–4.4 |
| SC-001a retry_after | §4.3 |
| SC-002a 并发 | §4.5 |
| SC-003 额度/null | §4.1, §4.4 |
| SC-005 防泄漏 | §2, §4.1 |
| SC-006 取消 | §4.6 |
