# V0.2 API 协议兼容基线

## 1. 兼容承诺

V0.2 对 OpenAI、Anthropic 和 Google Vertex AI 实行**同协议原生透传**：客户端使用哪一种厂商协议，平台就以该协议接收、转发并返回。平台不提供跨协议转换，也不把某厂商响应伪装成另一厂商格式。

“全兼容”在 V0.2 中定义为：对发布冻结日之前进入厂商公开稳定版的模型数据面 API，按端点目录逐项通过请求、响应、流式、错误、工具调用、文件和异步生命周期契约测试。Preview、Beta、实验性接口不计入稳定版发布承诺；如提供，必须逐项显式开启并标注风险。

## 2. 端点目录治理

SF01 维护机器可读、可版本化的 Endpoint Catalog。每条记录至少包含：provider、protocol version、method、path/template、稳定性、能力标签、是否有状态、传输形态、资源亲和规则、计量来源、首次支持版本和测试夹具版本。

- 目录内稳定端点：按目录能力转发。
- 未登记端点：以平台统一错误 `ENDPOINT_NOT_CATALOGED` 拒绝。
- 控制面端点：以 `CONTROL_PLANE_NOT_ALLOWED` 拒绝。
- 共享 Project 调用有状态端点：以 `DEDICATED_PROJECT_REQUIRED` 拒绝。
- 新增或改变目录记录必须经过评审、兼容测试与版本发布，不能自动暴露厂商新接口。

## 3. 明确排除的控制面

账号、组织、IAM、支付、账单账户、上游凭据管理及类似厂商管理控制面不在代理范围。平台自身 Provider Connection 的凭据管理属于 TokenMarket 管理面，不等于代理厂商凭据管理 API。

## 4. 协议完整性要求

- 保留厂商定义的 HTTP 方法、路径变量、query、请求体、响应体、状态码和必要响应头。
- 除鉴权替换、目标路由和平台安全限制外，不重命名、不丢弃合法字段。
- 支持未知但合法的扩展字段透传；不得因本地 DTO 未声明而静默删除。
- SSE 事件顺序、事件类型、终止语义和错误语义与厂商协议一致。
- WebSocket 的握手、双向事件、关闭码和资源亲和必须保持一致。
- 工具/函数调用、结构化输出、多模态内容、文件、批处理和长任务资源 ID 不得被跨协议重写。
- 平台错误与 upstream 原生错误可区分；upstream 请求 ID 在安全允许范围内保留。

## 5. 厂商基线

### OpenAI

覆盖发布冻结日公开稳定的数据面，包括 Responses、Chat Completions、模型查询，以及稳定的音频、图像、嵌入、Moderation、Files、Uploads、Batches、Fine-tuning、Vector Stores 和 Realtime 能力。具体端点以 Endpoint Catalog 为唯一发布清单。

官方参考：[Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)、[Chat Completions API](https://developers.openai.com/api/reference/cli/resources/chat/subresources/completions)、[Files API](https://developers.openai.com/api/reference/cli/resources/files)、[Realtime 模型说明](https://developers.openai.com/api/docs/models/gpt-realtime)。

### Anthropic

覆盖发布冻结日公开稳定的数据面，包括 Messages、Message Batches、Token Counting 与 Models；Beta 能力不属于稳定承诺，只有经显式目录登记和 Project opt-in 后才可开放。

官方参考：[Anthropic API Overview](https://platform.claude.com/docs/en/api/overview)。

### Google Vertex AI

覆盖发布冻结日公开稳定的 Vertex AI Publisher Model 数据面，包含目录登记的生成、流式生成、计数、嵌入、预测、批任务、缓存和调优资源操作；区域、项目和资源路径由 Provider Connection 与专享绑定确定。

官方参考：[Vertex AI Publisher Models REST](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1beta1/projects.locations.publishers.models)。稳定性以冻结时厂商文档标识和目录评审结果为准，不能仅从 URL 中是否含 `beta` 推断。

## 6. 兼容验收

每条发布目录记录至少具备：正向请求、非法参数、鉴权失败、upstream 限流、upstream 5xx、超时/断连、未知字段、流式或资源生命周期（适用时）、工具调用（适用时）以及计量提取测试。三厂商稳定端点目录覆盖率和合同测试通过率均须达到 100%。
