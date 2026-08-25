# Quickstart Validation：火山方舟请求与响应兼容

**Purpose**: 用 **受控 HTTP 替身**（非真实火山）在 `proxy-gateway` 单测中验证
SF07 字段过滤、非流式标准化、SSE 分帧、usage 完整性、失败分界与防泄漏。

**Contracts**: [contracts/](./contracts/)  
**Data model**: [data-model.md](./data-model.md)  
**Research**: [research.md](./research.md)

本文是实现后的验收指南，不含完整实现代码。命令默认从仓库根目录执行。

V0.1 **不**挂载公开或内部 HTTP 适配路由；验收入口是 `go test`。

## 1. Prerequisites

- `.tool-versions` 中的 Go 1.25.x 可用。
- **不依赖** PostgreSQL 业务表。
- **禁止** 将真实火山 API Key 写入仓库、夹具、本文件或 CI 日志。
- 替身 Base URL 仅出现在测试内 `httptest.Server`，不要指向生产方舟。

示意环境（实现名可微调，语义锁定）：

```bash
# 仅文档；测试代码注入等价值
VOLCANO_CHAT_BASE_URL=http://127.0.0.1:0/api/v3
VOLCANO_CHAT_DEFAULT_DEADLINE_SECONDS=60
VOLCANO_CHAT_MAX_DEADLINE_SECONDS=300
VOLCANO_CHAT_MAX_BODY_BYTES=2097152
VOLCANO_V01_CHAT_MODELS=doubao-pro-32k,doubao-lite-32k
VOLCANO_CHAT_MODEL_MAP=
VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS=5
VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS=300
```

## 2. Bootstrap and unit/contract tests

```bash
make toolchain-check
make bootstrap
cd services/proxy-gateway && go test ./internal/domain/chatcompat/ ./internal/application/ ./internal/infrastructure/platform/volcano/ -count=1 -race
```

Expected:

- 允许列表：扩展采样集通过；`tools` / `response_format` / `n=2` / 未知顶层键 → `unsupported_parameter` 且无上游调用。
- `messages[].content` 为 parts / image_url 时 **不得**被拒绝。
- `quota` 无关：本包不出现假 0 usage。
- `choices` 缺失 → `invalid_response`；choices 在且 usage 缺 → `success` + `usage_status=missing`。
- 429 无 Retry-After → `retry_after_seconds=5`。
- 流：拆包/合包；零事件 401 → 结构化 `invalid`；已出 delta 后 EOF → `truncated_stream` 且无 `[DONE]`。
- 日志 helper 扫描无完整 Key、无 message 正文。
- 相关包行覆盖 ≥80%。

## 3. Golden / SSE fixtures

实现应在 `internal/infrastructure/platform/volcano/fixtures/` 放置合成金标
（成功非流式、缺 usage、畸形 body、多块 SSE、末块 usage、截断）。禁止真实 Key。

```bash
cd services/proxy-gateway && go test ./internal/infrastructure/platform/volcano/ -count=1 -run 'Usage|SSE|Allowlist'
```

## 4. Deadline and cancel

```bash
cd services/proxy-gateway && go test ./internal/application/ -count=1 -run 'Deadline|Cancel|NoRetry'
```

Expected:

- 调用方不设截止 + 上游阻塞 → ≤60s 以 `timeout` 结束。
- 调用方 100ms 取消 → 迅速返回；已出事件则 truncated 且不补 DONE。
- 5xx **不得**自动重试生成请求（上游调用计数 = 1）。

## 5. Contract assets

```bash
cd services/proxy-gateway && go test ./internal/domain/chatcompat/ -count=1 -run Contract
```

Expected：`shared/contracts/volcano-openai-compat/v1/`（实现提升后）或本功能
`specs/007-volcano-openai-compat/contracts/` 下 OpenAPI 可解析；枚举与
`error-classification.md` 一致。

## 6. Static gates

```bash
make lint
make type-check
make test
make security-check
```

Expected：无真实 Key 入仓；夹具仅合成。

## 7. Out of scope for this quickstart

- 真实火山联调（可选人工，不入默认 CI）
- 公开 `POST /v1/proxy/volcano/chat/completions`（SF12/SF15）
- Key 选择、买家认证、用量落账

## 8. Traceability

| Spec | Quickstart step |
|------|-----------------|
| SC-001 兼容测试集 | §2, §3 |
| SC-002 转换 SLO | CI：禁止 ReadAll（§2）；合入：`go test -bench` 写入 evidence，不对 5 ms/1 ms 墙钟 fail CI |
| SC-002a 60s | §4 |
| SC-003 字段策略 | §2 允许列表 |
| SC-004 分类 + 流分界 | §2, §4 |
| SC-005 SSE 10k | CI：`sse_scale_test.go` ≥10_000 确定性事件；§3 边界夹具 + fuzz 为补充 |
| SC-006 防泄漏 | §2 |
| SC-007 usage | §2, §3 |
