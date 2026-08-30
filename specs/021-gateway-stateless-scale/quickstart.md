# Quickstart：021 无状态网关

```bash
cd services/proxy-gateway
go test ./internal/domain/runtimesnap/ ./internal/httpserver/ ./internal/domain/usageobs/ -count=1 -race
```

期望：快照切换无混用；Drain 拒绝新请求；删除 WAL 目录后 Load 仍成功。
