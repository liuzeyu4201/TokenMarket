# Phase 0 Research：Vertex 稳定数据面

## Decision 1：ResourceID 忽略 Google context 变量

project/location/publisher/model 不是亲和主键；operation/batchPredictionJob/cachedContent/tuningJob 才是。

## Decision 2：创建响应登记 `name` 最后一段

Vertex LRO 常用 `{"name":"projects/.../operations/op"}`，tee 提取最后一段作为 resource_id。
