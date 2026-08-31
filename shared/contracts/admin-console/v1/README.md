# admin-console v1

Version: 1.0.0（SF31 运营管理后台）

独立管理员控制台，前缀 `/admin/v1`，Cookie 沿用
`admin-identity/v1` 的 `__Host-tokenmarket_admin_session`（Path=`/admin`）。
不复用买家 `__Host-tokenmarket_session`。

## 范围

- 分页运营目录：user、session、connection、project、price、route、ledger、
  alert、audit。
- 价格/路由草稿→差异→仿真→审批→发布/回滚；禁止 PATCH active。
- 高风险向导：专享更换、冲正、强退会话；取消/超时无半完成状态。
- Connection 仅指纹/能力/健康；无明文凭据、导出或网络字段。

## 禁止

SQL 编辑器、任意字段 patch、删除账本/审计、设置最终余额、
`credential.read`。

HTTP 契约：[`admin-console.openapi.yaml`](./admin-console.openapi.yaml)。
RBAC 只读扩展见 `admin-identity/v1/rbac.md`。
