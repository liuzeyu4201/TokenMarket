# observability v1

Version: 1.0.0（SF32 全链路可观测、SLO 与告警）

- Trace：同一 `request_id` 串联 proxy/route/upstream/usage/ledger；异步 hop `kind=link`。
- 标签允许列表见 [`labels.md`](./labels.md)；禁止 user/project/request ID。
- SLO：数据面 99.9%，管理面 99.5%，30 天窗口；剩余错误预算 <20% 冻结发布。
- 告警目录见 [`alerts.md`](./alerts.md)。
- 遥测脱敏：无 prompt/response、文件内容、密钥、token、验证码、手机号明文。
