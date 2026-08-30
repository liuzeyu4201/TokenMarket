# Phase 0 Research：单会话加固

## Decision 1：PostgreSQL 世代为唯一授权依据

**Decision**: `users.session_generation` 单调递增；`auth_sessions.session_generation` 写入签发时的世代。引导时两者必须相等且行未撤销。不把 Redis 正向缓存「会话有效」。

**Rationale**: SF07 要求缓存异常不能复活已撤销会话。V0.1 仅撤销行，节点若缓存会话摘要可能滞后。世代使旧 cookie 在提交后立即全局失效。

**Alternatives**: 仅 Redis pub/sub 通知 — 缓存中断会漏通知。

## Decision 2：全部退出提升世代；当前退出只撤销本行

**Decision**: `DELETE /session` 保持精确撤销当前 cookie。`POST /api/v1/auth/session-revocations` `{scope:"all"}` 提升世代并撤销全部未撤销 Web 会话。

**Rationale**: 丢失设备需要结束全部 Web 会话；当前退出不必惩罚尚未发生的新登录。

## Decision 3：安全页只返回脱敏摘要

**Decision**: `GET /api/v1/auth/security-summary` 需有效会话。返回签发/过期时间、世代、来源摘要（HMAC 截断，非完整 IP）、最近认证事件结果。不含 cookie/token。

**Rationale**: 异常登录可感知且不扩大攻击面。
