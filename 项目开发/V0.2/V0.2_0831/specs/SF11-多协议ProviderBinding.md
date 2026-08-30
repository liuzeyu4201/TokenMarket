# SF11 多协议 Provider Binding

**优先级：** P0　**依赖：** SF01、SF10

## 功能描述

Provider Binding 描述一个 Project 对某协议使用的厂商、区域、模型/端点策略及供给方式。Project 可同时配置 OpenAI、Anthropic、Vertex，但请求必须按原协议命中对应 Binding。

## 功能要求

- 每个 Project+protocol 只有一个生效 Binding；配置采用草稿、校验、发布版本流程。
- shared Binding 定义可接受厂商/模型/区域和预算限制；dedicated Binding 指向唯一专享 Connection。
- Binding 发布前验证 Project mode、协议能力、连接状态和价格可用性。
- 请求进入时锁定 Binding version；修改/停用只影响后续请求。
- 提供 SDK 所需原生 base URL、鉴权方式和协议版本提示，不暴露 upstream 凭据。

## 边界与异常

Binding 不执行跨协议映射。一个 OpenAI 协议请求不能因模型名称相近而送入 Anthropic 或 Vertex 协议。

## 验收标准

1. 同一 Project 可同时发布三协议 Binding，分别得到正确原生入口。
2. 同一 Project+protocol 并发发布只产生一个 active version。
3. Project mode 与 Binding 模式不一致时保存/发布均被拒绝。
4. 在途请求继续使用锁定版本，新请求在传播 SLA 内使用新版本。
5. 直接篡改 protocol/provider/model 参数不能绕过 Binding 约束。
6. 删除或失效专享 Connection 会使 Binding 明确 degraded，不会回退共享池。

## 验收证据

版本并发测试、三协议 E2E、模式约束测试、配置切换测试和降级状态截图。
