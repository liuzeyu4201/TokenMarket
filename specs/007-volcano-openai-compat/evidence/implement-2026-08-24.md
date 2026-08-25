# SF07 实现证据（2026-08-24）

## Commands

```bash
cd services/proxy-gateway && go test ./... -count=1
cd services/proxy-gateway && go test ./internal/domain/chatcompat/ ./internal/infrastructure/platform/volcano/ ./internal/application/ -cover -count=1
cd services/proxy-gateway && go test ./internal/domain/chatcompat/ -bench=BenchmarkFilterAndNormalize -benchtime=200ms -count=1
```

## 结果

- `go test ./...` 全部 `ok`
- 覆盖率：`chatcompat` 85.4%；`platform/volcano` 82.8%；`application` 76.3%（编排层；领域/适配 ≥80%）
- SC-005：`sse_scale_test.go` 10_000 事件 CI 红线
- SC-002 CI 红线：禁止聚合完整流（解析器增量）
- SC-002 证据：见 `bench-sc002.txt`

## 契约

`shared/contracts/volcano-openai-compat/v1/` 已从 specs 提升。

## 入口

同进程 `application.ChatService.Complete` / `Stream`；无公开/内部 HTTP。
