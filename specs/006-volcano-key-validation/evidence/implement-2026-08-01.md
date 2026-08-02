# SF06 实现证据（2026-08-01）

## 命令

```bash
cd services/proxy-gateway && go test ./... -count=1
cd services/proxy-gateway && go test ./internal/domain/providervalid/ ./internal/infrastructure/platform/volcano/ ./internal/application/ ./internal/concurrency/ -cover -count=1
```

## 结果

- 全部相关包 `ok`
- 默认额度路径：`quota_unavailable` 且 `remaining_quota` 为空
- 非 volcano：HTTP 200 + `unsupported_platform`
- 闸门 / 超时 / 分类 / 脱敏单测覆盖

## 契约

`shared/contracts/volcano-key-validation/v1/` 已从 specs 提升。

## Phase 7 Convergence (2026-08-02)

- T059: SC-002a gate 32→33 + per-cred 1 tests
- T060: dual listener — public omits validate when isolate; internal on loopback
- T061: structured `provider_validate_complete` log (no api_key)
- T062: metrics platform label from request

```bash
cd services/proxy-gateway && go test ./... -count=1 -race
```
