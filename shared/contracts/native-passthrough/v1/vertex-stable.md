# Vertex 稳定数据面：native-passthrough v1.4

**Owner**: Proxy Gateway

冻结日 Endpoint Catalog 中 `provider=vertex` 且 `stability=stable` 的记录必须经同协议内核可达。

- 覆盖率分母等于上述记录数。
- 原样转发 Google project/location/publisher/model 路径段，内核不得改写。
- long-running `name` 与 batch/cache/tuning 资源 ID 亲和 fail-closed。
- IAM/endpoint 控制面平台拒绝；信封不得伪装 `google.rpc.Status`。
- v1beta1 等 preview 默认拒绝。

`TOKENMARKET_VERTEX_SMOKE` 显式启用真实冒烟。
