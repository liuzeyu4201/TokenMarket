# SF21 Google Vertex 稳定数据面全兼容

**优先级：** P0　**依赖：** SF01、SF18、SF22

## 功能描述

对 Endpoint Catalog 冻结的 Google Vertex AI 公开稳定 Publisher Model 数据面提供原生兼容，保留 Google 项目、区域、资源名、鉴权、流式、工具和长任务语义。

## 功能要求

- 支持目录内 generate/stream generate、count tokens、embed、predict 等稳定方法及其原生路径。
- 支持目录内 batch、cached content、tuning/operation 等有状态资源生命周期。
- Provider Connection 明确 Google project、location、publisher/auth scope；客户端不能越权替换为其他项目或区域。
- 保留 Google REST/RPC 错误、operation、resource name、usage metadata 和流式帧。
- 函数调用、多模态、结构化输出等能力按目录原生字段透传。

## 边界与异常

不代理 Google Cloud IAM、billing、service account/key 管理等控制面。稳定性由冻结时官方标识与目录评审共同确定，不仅根据 URL 是否含 `beta` 判断。

## 验收标准

1. 冻结目录全部 stable Vertex 记录合同测试通过率 100%。
2. 生成、流式、token count、embedding、工具、多模态各有真实 Vertex 冒烟。
3. project/location/resource name 篡改无法越出 Binding/Connection 授权范围。
4. batch/cache/tuning 等目录有状态能力仅在 dedicated Project 完成生命周期测试。
5. Google long-running operation 轮询/取消始终回到原 Connection。
6. 原生错误与直连基准可识别等价，平台错误不伪装为 `google.rpc.Status`。

## 验收证据

目录覆盖、路径授权测试、流式/工具差分、operation 亲和测试和真实冒烟记录。
