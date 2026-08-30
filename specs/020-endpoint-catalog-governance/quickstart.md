# Quickstart：验证 020-endpoint-catalog-governance

## 前置

- 仓库根目录；已 `make bootstrap`（或至少 gateway `go test` 与 workflow pytest 可用）。
- 不需要 Docker、真实厂商密钥或网络。

## 场景 A — 目录校验与确定性生成

```bash
# 仓库级契约与目录测试
uv run --project tools/workflow pytest tests/workflow/test_endpoint_catalog.py tests/workflow/test_contracts.py -q
```

期望：schema/完整性通过；`CATALOG.md` 二次生成字节相同；总表包含新契约。

## 场景 B — 准入判定（无上游）

```bash
go test ./internal/domain/endpcatalog/ -count=1 -race
```

在 `services/proxy-gateway` 下执行。期望：

- stable HTTP 无状态 → allow
- preview 无 opt-in → `PREVIEW_NOT_ENABLED`
- control_plane → `CONTROL_PLANE_NOT_ALLOWED`
- 未知 path → `ENDPOINT_NOT_CATALOGED`
- shared + stateful → `DEDICATED_PROJECT_REQUIRED`

## 场景 C — 主版本失败关闭

设置不兼容 `TOKENMARKET_CATALOG_MAJOR`（或测试夹具）后加载必须返回
`CATALOG_VERSION_MISMATCH`。Gateway/API/Billing/Admin 启动路径覆盖此失败。

```bash
go test ./internal/domain/endpcatalog/ -count=1 -run Version
# Python 服务
uv run --project services/api-service pytest services/api-service/tests/unit/test_endpcatalog.py -q
uv run --project services/billing-service pytest services/billing-service/tests/unit/test_endpcatalog.py -q
uv run --project services/admin-service pytest services/admin-service/tests/unit/test_endpcatalog.py -q
```

## 场景 D — 契约可解析

打开并解析：

- `shared/contracts/endpoint-catalog/v1/catalog.schema.json`
- `shared/contracts/project/v1/project.openapi.yaml`
- `shared/contracts/provider-connection/v1/provider-connection.openapi.yaml`
- `shared/contracts/route-decision/v1/route-decision.schema.json`
- `shared/contracts/usage/v1/usage-observation.schema.json`
- `shared/contracts/pricing/v1/pricing.schema.json`
- `shared/contracts/ledger/v1/ledger-entry.schema.json`
- `shared/contracts/audit/v1/audit-event.schema.json`

期望：OpenAPI 含 `openapi` 键；JSON Schema 含 `$schema`；账本 schema 无
update/delete；Connection schema 无明文读回。

## 非目标

不要在本功能 quickstart 中调用真实 OpenAI/Anthropic/Vertex。那是后续 SF 的
授权冒烟，不是 SF01 完成条件。
