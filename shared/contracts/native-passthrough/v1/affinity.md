# 资源亲和：native-passthrough v1.1

**Owner**: Proxy Gateway

目录 `affinity=resource_id` 的端点：创建响应登记 `(protocol, resource_id) → connection_id`。  
后续 GET/DELETE/POST 带该 ID 的请求必须使用原 Connection。缺失或冲突 fail-closed，禁止重选。

`affinity=connection`（如 realtime WebSocket）：握手成功后该 TCP 会话固定 Connection。

更换 dedicated Connection 不改写既有映射。
