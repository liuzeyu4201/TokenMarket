# Evidence 052

`go test ./internal/capacity/ -count=1 -timeout 120s` ok，覆盖率 87%。

- Profile 常量锁定 500 租户 / 500 RPS / 30m / 1000 RPS / 5m / 500 流 / 2h / RPO 5m / RTO 30m。
- 稳态 1s 窗口达到 ≥90% 的 500 RPS，成功率 100%，平台 p95 ≪ 100 ms。
- 突发 1000 RPS 后注入 upstream 故障再恢复，账本 open=0、无双扣。
- 500 条 SSE 经透传内核，断开率门槛通过，堆增长受控。
- 备份快照恢复：RPO 4 分钟 ≤5 分钟，RTO 远小于 30 分钟；故障后写入不出现在恢复实例。
- 同一引擎连续 3 次稳态达标。
- `CAPACITY_FULL=1` 跑墙钟 30m/5m/2h；真实厂商冒烟未授权，列为发布阻塞项。
