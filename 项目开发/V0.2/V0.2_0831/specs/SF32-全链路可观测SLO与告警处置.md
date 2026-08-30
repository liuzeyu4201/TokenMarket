# SF32 全链路可观测、SLO 与告警处置

**优先级：** P0　**依赖：** SF02、SF04、SF15、SF24、SF29

## 功能描述

建立从代理请求到路由、upstream、用量、结算和审计的全链路可观测性，按数据面/管理面 SLO 监控并提供可执行告警和运行手册。

## 功能要求

- 统一 request/trace ID 跨 Gateway、服务、事件和 worker；异步链路使用 link 关联。
- RED 指标按 protocol/endpoint/status 分类，控制高基数；路由、容量、连接健康、事件积压、未决账务有专用指标。
- 区分平台新增延迟和 upstream 延迟；SSE/WebSocket 记录建连、首事件、持续时间和关闭原因。
- SLO：数据面 99.9%，管理 API/UI 99.5%；定义 SLI、窗口、错误预算和发布停止规则。
- 告警包含影响、阈值、dashboard、runbook、owner 和升级路径；日志/trace 统一脱敏。

## 边界与异常

不记录完整 prompt/response、文件内容、密钥、token、验证码或手机号明文。指标不得用 user/project/request ID 作为无界 label。

## 验收标准

1. 任意抽样 request ID 可串联代理、路由、upstream、usage 和 ledger 状态。
2. SLO 仪表盘能分别计算数据面和管理面可用性/延迟与错误预算。
3. upstream 慢、无候选、事件积压、未决突增、连接故障各触发正确告警。
4. 逐项告警演练在值班目标时间内被发现、定位并按 runbook 处置。
5. 高基数保护压力测试下监控系统资源受控。
6. 自动敏感信息扫描在日志、trace、metric exemplar 中零命中测试 secret。

## 验收证据

dashboard、trace 样例、SLI 查询、告警演练、基数压测和脱敏扫描结果。
