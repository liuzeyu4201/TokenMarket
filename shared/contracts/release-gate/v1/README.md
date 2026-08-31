# release-gate v1

Version: 1.0.0（SF34 发布门禁）

硬门禁失败则公开上线 **no-go**：

- SF01–SF34 追踪 100%
- 稳定端点合同 100%
- 关键 E2E 100%
- 变更领域覆盖率 ≥80%；鉴权/路由/权限/账本 ≥90%
- P0/P1 = 0；安全 Critical/High = 0
- 独立渗透 Critical/High 已关闭
- 连续 3 次关键自动化无 flaky

P2/Medium 必须有 owner、期限、影响。未授权的渗透、真实短信、付费冒烟、生产部署列为发布阻塞项。
