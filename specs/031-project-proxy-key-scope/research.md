# Phase 0 Research：Project 代理 Key

## Decision 1：扩展既有 proxy_keys 表而非新表

**Decision**: Alembic 0013 增加 project_id（可空，兼容 volcano）、协议/模型/CIDR 数组、额度、过期。新签发必须带 project_id。

**Rationale**: 网关已按 secret_hash 查找；换表会打断 V0.1 认证。

## Decision 2：鉴权 HMAC + compare_digest

**Decision**: 存储 HMAC-SHA256(pepper, secret)。查找后 `hmac.compare_digest`；未命中与 dummy 比较。对外一律失败同形。

**Rationale**: FR-005。

## Decision 3：配额原子递增

**Decision**: `proxy_key_quota(key_id, period_start, accepted)`。`UPDATE … WHERE accepted < limit RETURNING`。无行则 INSERT 1。并发超发 = 0。

**Rationale**: SC-003。额度是请求次数，不是金额（SF13）。

## Decision 4：网关正向缓存 1s

**Decision**: `defaultPosTTL = 1s`。撤销后新请求最多 1s 内仍可能命中缓存，满足 ≤1s SLA。负向缓存保持 2s。

**Rationale**: 原 30s 违反撤销 SLA。

## Decision 5：限制取交集

**Decision**: authorize 依次检查 status、expiry、protocol、model、CIDR、quota。任一项失败即拒绝。

## Decision 6：火山路径保留

**Decision**: `POST /api/v1/proxy-keys` 仍签发 volcano、无 Project。`POST /api/v1/projects/{id}/proxy-keys` 为 V0.2 路径。
