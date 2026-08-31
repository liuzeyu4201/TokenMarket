# 发布 go/no-go

**Owner**：发布负责人  
**契约**：`shared/contracts/release-gate/v1/`

## 硬门禁（失败即 no-go）

- SF01–SF34 追踪 100%
- 稳定端点合同 100%
- 关键 E2E 100%
- 覆盖率：变更领域 ≥80%；鉴权/路由/权限/账本 ≥90%
- P0/P1 = 0；安全 Critical/High = 0
- 独立渗透 Critical/High 已关闭并复测
- 同一候选 commit 连续 3 次 `make ci` 无 flaky

## 公开上线 vs 实现完成

缺渗透、真实短信、付费厂商冒烟、生产凭据、push 或生产部署时：

- **公开上线** = no-go
- **实现完成** = go-with-blockers，阻塞项必须点名

回滚不得删除账本或用量事实。
