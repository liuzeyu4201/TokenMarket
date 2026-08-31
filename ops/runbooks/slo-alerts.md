# SLO 与全链路告警处置

**Owner**：proxy-gateway on-call（账务类转 billing-service；连接类转 supply_ops）  
**Dashboard**：Grafana `v02-slo-overview`  
**升级**：P1 15 分钟未定位则升级 P0。错误预算告警立即冻结发布。

## 通用步骤

1. 从告警页面复制 `request_id`（若无则从最近失败 hop 列表取）。
2. 用同一 ID 查看 proxy → route → upstream → usage → ledger。缺失段标 unknown，不要把过期数据当实时。
3. 区分平台新增延迟与 upstream 延迟。
4. 按 kind 执行下面专节，完成后在告警中留下处置摘要。

## upstream_slow

影响：买家延迟上升。阈值：upstream p95 > 2s / 5m。  
检查上游健康与容量；不要把平台排队误判为上游。

## no_candidate

影响：无合格路由，失败关闭。阈值：5 分钟增量 > 0。  
检查资格过滤与目录冻结；专享不得回退共享池。

## event_backlog

影响：用量/结算积压。阈值：深度 > 1000。  
检查 worker 与 outbox；不要丢弃事件来“清空”积压。

## unresolved_spike

影响：未决账务突增。阈值：15 分钟增量 > 10。  
未决不得记 0；走对账/冲正向导，禁止改最终余额。

## connection_unhealthy

影响：连接探测失败。阈值：unhealthy > 0。  
只看指纹/健康；过期探测标 unknown/stale，禁止回读明文。

## 脱敏

日志、trace、exemplar 不得出现密钥、token、验证码、手机号明文或完整 prompt/response。
