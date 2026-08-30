# Phase 0 Research：工作区切换

## Decision 1：会话列 workspace，不信请求头

**Decision**: `auth_sessions.workspace ∈ {buyer, seller}`。`POST /api/v1/auth/workspace` 在 CSRF/Origin 通过后更新该列。`AuthorizationService.authorize(workspace=...)` 只接受调用方从会话读出的值。

**Rationale**: 总纲规定 UI 不是安全边界。

**Alternatives**: 每请求 Header `X-Workspace` — 标签页可伪造，导致串权。

## Decision 2：both 默认 buyer；固定角色不可切换

**Decision**: 登录时 buyer→buyer，seller→seller，both→buyer。切换目标必须 `workspace_allowed(role, target)`。

**Rationale**: 未授权切换必须 403。

## Decision 3：生效角色 = 工作区透镜

**Decision**: `effective_role = workspace`（buyer/seller），再查矩阵。账户角色 both 只表示「允许切换到该透镜」。账户 buyer 即使会话被篡改为 seller 也拒绝（不匹配则 ROLE_DENIED）。

**Rationale**: 切换不能扩大角色。
