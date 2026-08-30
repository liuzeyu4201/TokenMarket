# Data Model：卖家工作台

## QuoteRevision

(seller_id, connection_id, seq, multiplier_bps, rate_version, created_at, actor_id)  
主键追加 seq，禁止 UPDATE。

## DeclaredCapacity

connection_id → non-negative int（0 表示不接新共享请求）

## AuditEvent

actor, action, connection_id, before, after, timestamp

## WorkbenchCard（公开）

connection 安全元数据、当前报价、容量、health、admits_new、earnings.settled / unresolved。不得含 buyer_multiplier_bps。
