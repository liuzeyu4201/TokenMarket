# SF19 OpenAI 稳定数据面全兼容

**优先级：** P0　**依赖：** SF01、SF18、SF22

## 功能描述

对 Endpoint Catalog 冻结的 OpenAI 公开稳定模型数据面提供原生兼容，覆盖普通、流式、工具、多模态、文件、异步和 Realtime 形态。兼容范围以 SF01 目录而非手写概括为准。

## 功能要求

- 覆盖目录中的 Responses、Chat Completions、Models 及稳定音频、图像、嵌入、Moderation 等推理端点。
- 覆盖稳定 Files、Uploads、Batches、Fine-tuning、Vector Stores 等资源生命周期端点。
- 支持 function/built-in/MCP tool、structured output、多模态输入输出、background 与 streaming 等目录能力。
- 支持目录登记的 Realtime WebRTC/WebSocket/SIP 相关数据面入口；需要连接亲和的资源固定到原 Connection。
- 保留 OpenAI 原生请求 ID、错误、usage 和流事件；只替换平台代理鉴权。

## 边界与异常

不代理 OpenAI 账号、组织、项目/IAM、支付、账单或 API key 管理。Preview/Beta 只有目录显式标记且 Project opt-in 才开放。

## 验收标准

1. 冻结目录全部 stable OpenAI 记录具有合同测试且通过率 100%。
2. 文本、图像/音频/文件、工具调用、structured output 各至少一条真实厂商冒烟通过。
3. 流式事件顺序、终止原因、usage 和错误与直连基准语义一致。
4. 文件→引用→删除、batch/fine-tuning 等适用资源生命周期在 dedicated Project 端到端通过。
5. shared Project 调用目录标记 stateful 的端点稳定返回 `DEDICATED_PROJECT_REQUIRED`。
6. control-plane 与未登记路径分别返回 `CONTROL_PLANE_NOT_ALLOWED`、`ENDPOINT_NOT_CATALOGED`。

## 验收证据

目录覆盖报告、官方/代理差分 fixture、真实冒烟记录、资源生命周期 E2E 和拒绝测试。
