# Data Model：供给生命周期

## ProviderConnection（扩展）

| 字段 | 约束 |
|------|------|
| lifecycle_state | draft \| verified \| listed \| bound \| paused \| draining \| retired |
| supply_mode | shared \| dedicated；listed 起不可变（应用层 + 测试） |

## 转换

draft→verified（验证成功）；verified→listed（上架）；listed→bound（专享绑定）；listed/bound→paused；paused→listed/bound（resume）；listed/bound/paused→draining；draining/paused/verified/draft→retired（无阻塞）。

## 阻塞

code: BINDING_ACTIVE \| IN_FLIGHT \| UNSETTLED \| MODE_LOCKED \| ILLEGAL_STATE

## 索引

`uq_bindings_dedicated_connection`：dedicated + status∈{active,degraded} 时 connection_id 唯一。
