# SF20 Anthropic 稳定数据面全兼容

**优先级：** P0　**依赖：** SF01、SF18、SF22

## 功能描述

对 Endpoint Catalog 冻结的 Anthropic 公开稳定模型数据面提供原生兼容，重点保证 Messages 的内容块、工具调用和 SSE 事件语义，以及批处理、token 计数和模型查询。

## 功能要求

- 原生支持 stable Messages，包括 system/content blocks、多模态、tool use/result、thinking 等目录稳定能力。
- 原生支持 streaming 事件类型、顺序、增量字段、stop reason 和 usage。
- 支持 stable Message Batches、Token Counting 与 Models 生命周期/查询。
- 保留 `anthropic-version` 等必要版本 headers，并按目录控制允许版本。
- 保留 Anthropic 状态码、错误 envelope、request ID、rate-limit headers 和 usage。

## 边界与异常

Files、Skills、Agents、Sessions、Environments 等被官方标识为 Beta 的能力不属于稳定发布承诺；若试验开放，必须显式目录记录、Project opt-in 和独立测试。

## 验收标准

1. 冻结目录全部 stable Anthropic 记录合同测试通过率 100%。
2. 普通/流式 Messages、并行工具调用、多模态和 token count 的真实冒烟通过。
3. 每类 SSE 事件顺序和字段与直连 fixture 语义一致，无 OpenAI 风格重写。
4. Message Batch 创建、查询、结果和取消在 dedicated Project 完成生命周期测试。
5. 不支持/未 opt-in Beta 端点得到稳定平台拒绝，不被透明意外暴露。
6. upstream 限流、重载、非法请求和鉴权错误保持原生可识别性。

## 验收证据

目录覆盖、流事件差分、工具调用 fixture、batch E2E、真实冒烟与 Beta 负向测试。
