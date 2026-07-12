# Anthropic 平台（Claude）深度调研报告

> **调研日期**：2026-07-10  
> **数据来源**：Anthropic 官网、官方定价页、ToS 条款、第三方分析文章及社区反馈  
> **免责声明**：以下价格、限额与条款均基于公开信息整理，Anthropic 可能随时调整。请以 [claude.com/pricing](https://claude.com/pricing) 及 [anthropic.com/legal](https://www.anthropic.com/legal) 的实时页面为准。

---

## 目录

1. [Claude Pro（$20/月）](#1-claude-pro20月)
2. [Claude Max 计划（$100/$200/月）](#2-claude-max-计划100200月)
3. [Claude API 按量付费与 Rate Limits](#3-claude-api-按量付费与-rate-limits)
4. [额度与过期机制](#4-额度与过期机制)
5. [ToS 与转售条款](#5-tos-与转售条款)
6. [模型能力关键参数](#6-模型能力关键参数)
7. [支付方式与地区限制](#7-支付方式与地区限制)
8. [总结与风险提示](#8-总结与风险提示)

---

## 1. Claude Pro（$20/月）

### 1.1 平台名称与套餐名称
- **平台**：Anthropic Claude（claude.ai）
- **套餐**：Claude Pro（个人订阅版）

### 1.2 定价
| 计费方式 | 价格 |
|---------|------|
| 月付 | **$20/月** |
| 年付 | **$200/年**（等效 $17/月，约省 15%） |

> 价格不含适用税费。Anthropic 可能根据地区显示本地货币价格，但基准为美元。

### 1.3 Token 额度与调用限制
Anthropic 对 Pro 计划采用**不公开具体数字的滚动配额制**，但社区和实测反馈给出了以下参考范围：

| 指标 | 参考值 |
|------|--------|
| 消息配额 | 约 **10–45 条消息 / 5 小时滚动窗口**（使用 Sonnet 时；Opus 更少） |
| 配额重置机制 | 5 小时滚动窗口 + 7 天每周上限 |
| 峰值时段 | 付费用户享有优先访问权，但 Pro 仍可能受服务器负载影响 |
| Claude Code | 共享同一条消息配额；使用 `ANTHROPIC_API_KEY` 时直接走 API 计费，不计入订阅配额 |

> 注意：Anthropic 官方描述为 "More usage"（约为 Free 的 5 倍），但**不公布精确 token 数或消息数**。实际能发多少条取决于消息长度、上下文大小、模型选择及服务器负载。

### 1.4 过期机制
- **订阅费用**：按月/年自动续费，**不设退款**（巴西、墨西哥、韩国、台湾等部分地区享有 7 天无理由取消权）。
- **未使用配额**：滚动窗口内未用完的额度不会 rollover（滚存）到下一周期；5 小时后按滚动窗口逐步释放。
- **取消订阅后**：已付费周期内仍可继续使用，至周期结束。

### 1.5 API 可用性
- **Claude Pro 本身不提供 API Key**。Pro 是面向消费者（claude.ai 聊天界面）的订阅计划，与 Claude API / Console 是**两套独立的计费体系**。
- 如需 API 调用，需额外前往 [console.anthropic.com](https://console.anthropic.com) 注册并购买 API Credits。
- Claude Code（终端版）在 Pro 订阅内可用，但**仅限通过官方 CLI (`claude`) 的交互式使用**。

### 1.6 ToS 相关条款（消费者条款）
> 来源：[Anthropic Consumer Terms of Service](https://www.anthropic.com/legal/consumer-terms)

关键限制摘要：
- **禁止共享账户**："You may not share your Account login information, Anthropic API key, or Account credentials with anyone else. You also may not make your Account available to anyone else."
- **禁止开发竞争产品**：不得使用服务开发任何竞争产品或服务，包括训练竞争性 AI 模型或转售（resell）服务。
- **禁止自动化访问（消费者端）**：除非通过 Anthropic API Key，否则禁止通过 bot、script 或其他非人工方式访问服务。
- **数据训练**：默认可能使用对话进行模型训练（2025 年 8 月后从 opt-in 改为默认 opt-out 需手动关闭），opt-out 后保留期为 30 天；opt-in 后为 5 年。

### 1.7 模型能力关键参数
- **默认模型**：Claude Sonnet（当前为 Sonnet 5，随 Anthropic 迭代更新）
- **上下文长度**：200K tokens（API 端 Opus/Sonnet 4.6+ 可选 1M tokens beta）
- **多模态**：支持文本 + 图像输入（不支持原生音频/视频）
- **Claude Code**：终端 AI 编程助手（Pro 及以上可用）
- **Claude Cowork / Design / Science**：扩展工作流能力
- **Projects**：无限项目空间，支持文档上传、持久化记忆
- **Web Search**：内置联网搜索
- **Artifacts**：生成文件、代码、图表等可视化输出
- **工具调用**：支持函数调用、MCP Connectors、Google Workspace / Slack 集成

### 1.8 支付方式
- **支持**：Visa、Mastercard、American Express、主流借记卡
- **不支持**：PayPal、Venmo、电汇（标准账户）、支付宝、微信支付、加密货币
- **要求**：账单地址必须与银行记录一致，且位于 Anthropic 支持的国家/地区列表内

---

## 2. Claude Max 计划（$100/$200/月）

### 2.1 平台名称与套餐名称
- **平台**：Anthropic Claude（claude.ai）
- **套餐**：Claude Max（5x）/ Claude Max（20x）

### 2.2 定价
| 套餐 | 月费 | 等效说明 |
|------|------|---------|
| Max 5x | **$100/月** | 约为 Pro 5 倍的会话容量 |
| Max 20x | **$200/月** | 约为 Pro 20 倍的会话容量 |

> Max 计划**仅支持月付**，无年付折扣。价格不含税费。

### 2.3 Token 额度与调用限制
| 指标 | Max 5x | Max 20x |
|------|--------|---------|
| 相对 Pro 配额 | **5x** | **20x** |
| 输出限制 | 更高 | 最高 |
| 优先访问 | 高流量时段优先 | 高流量时段优先 |
| 每周滚动限制 | 有（7 天滚动） | 有（7 天滚动） |

> 与 Pro 一样，Anthropic 不公开 Max 的精确 token 或消息数，仅描述为 "5x or 20x more usage than Pro"。

### 2.4 过期机制
- 与 Pro 相同：月付自动续费，**无 rollover**，未使用额度不累积。
- 在 2026 年 6 月计划调整前，Max 的额外使用量（超过订阅配额部分）可按 API 标准费率购买；该政策在 2026 年 6 月 15 日的 Agent SDK 分离计划中被暂停。

### 2.5 API 可用性
- Max 订阅本身**不附赠 API Key**。如需 API 访问，仍需单独购买 API Credits。
- 通过 Claude Code CLI 的交互式使用包含在订阅内，但 headless / 自动化脚本需使用 API Key。

### 2.6 ToS 相关条款
- 与 Pro 共用同一套 **Consumer Terms of Service**。
- 2026 年 2 月官方文档更新：Agent SDK 明确**要求 API Key 认证**，不得使用 Max/Pro 的 OAuth token 调用 Agent SDK。
- 2026 年 5 月 Anthropic 表示：Max 订阅的 "ordinary, individual usage"（普通个人使用）假设仍然成立；但若用于商业自动化或生产环境，官方建议使用 API Key。

### 2.7 模型能力关键参数
- 与 Pro 相同，但拥有更大的**会话配额**和**输出上限**。
- 享有新功能的**早期访问权（Early Access）**。
- 在高流量时段获得**优先访问权**。

### 2.8 支付方式
- 与 Pro 相同：仅接受信用卡/借记卡，不支持 PayPal、电汇、支付宝等。

---

## 3. Claude API 按量付费与 Rate Limits

### 3.1 平台名称与套餐名称
- **平台**：Anthropic API / Claude Developer Console（console.anthropic.com）
- **计费方式**：预付积分（Usage Credits）+ 按 token 消耗计费

### 3.2 定价（每百万 tokens，2026 年 7 月）

| 模型 | Input / MTok | Output / MTok | Prompt Caching (Write) | Prompt Caching (Read) | 备注 |
|------|-------------|--------------|----------------------|----------------------|------|
| **Fable 5** | $10.00 | $50.00 | $12.50 | $1.00 | 最新旗舰，长期 agent |
| **Opus 4.8** | $5.00 | $25.00 | $6.25 | $0.50 | 复杂编码与企业工作 |
| **Sonnet 5** | $2.00* | $10.00* | $2.50* | $0.20* | *Intro price 至 2026-08-31，之后标准价 $3/$15 |
| **Haiku 4.5** | $1.00 | $5.00 | $1.25 | $0.10 | 最快、最经济 |
| **Opus 4.7 (legacy)** | $5.00 | $25.00 | $6.25 | $0.50 | |
| **Sonnet 4.6 (legacy)** | $3.00 | $15.00 | $3.75 | $0.30 | |
| **Opus 4.1 (legacy)** | $15.00 | $75.00 | $18.75 | $1.50 | 即将退役 |

> **其他附加费用**：
> - Fast Mode（Opus 4.8）：**2x 标准价格**
> - US-only inference：**1.1x 标准价格**
> - Batch processing：**50% 折扣**
> - Managed Agents：$0.08 / 活跃 session 小时
> - Web Search：$10 / 1K 次搜索
> - Code Execution：每日每组织 50 小时免费，额外 $0.05 / 小时

### 3.3 Rate Limits（API 使用层级）

Anthropic 在 **2026 年 6 月 26 日** 将旧的 Tier 1–4 体系合并为新的三档体系：

#### 新体系（2026-06-26 起）

| Usage Tier | RPM | ITPM（Input TPM） | OTPM（Output TPM） | 月度支出上限 |
|-----------|-----|------------------|------------------|-------------|
| **Start** | 1,000 | 2,000,000 | 400,000 | $500 |
| **Build** | 5,000 | 5,000,000 | 1,000,000 | $1,000 |
| **Scale** | 10,000 | 10,000,000 | 2,000,000 | $200,000 |
| **Custom** | 协商 | 协商 | 协商 | 无上限 |

> - 以上限制适用于 **Opus 4.x / Sonnet 4.x / Haiku 4.5**，每个模型独立计算配额。
> - **Fable 5** 有独立限制：Start 500K ITPM / Build 1.5M / Scale 4M。
> - **Cache read tokens 不计入 ITPM**（prompt caching 优势）。
> - 突发流量可能触发 429，即使未达 tier limit。

#### 旧体系（参考，2026-05-08 前）

| Tier | 要求 | RPM | Input TPM | Output TPM | 备注 |
|------|------|-----|-----------|------------|------|
| Free / Build | 注册即可 | 5 | 20,000 | 4,000 | |
| Tier 1 | 验证信用卡并购买少量积分 | 50 | 40,000 | 8,000 | ~$5+ |
| Tier 2 | 累计消费 $40+ | 1,000 | 80,000 | 16,000 | 维持 14 天以上 |
| Tier 3 | 累计消费 $200+ | 2,000 | 160,000 | 32,000 | 维持 14 天以上 |
| Tier 4 | 累计消费 $400+ | 4,000+ | 400,000+ | 80,000+ | 最高自助 tier |

> 2026 年 5 月 Anthropic 曾大幅提升限额（Tier 1 从 30K 提到 500K ITPM），随后在 6 月 26 日合并为 Start/Build/Scale 体系。

### 3.4 过期机制
- **API Credits（预付积分）**：
  - 自**最近一次充值起 365 天（1 年）**后过期。
  - 过期后**未使用积分自动清零**，不可恢复、不可退款。
  - 积分**不可转让、不可退款**（除非在充值后 24 小时内完全未使用且符合特定条件）。
  - 账户关闭时，剩余积分被没收。
- **月度支出上限**：Start $500 / Build $1,000 / Scale $200,000。达到上限后 API 调用将被阻止，直到下个账单周期或手动提升。

### 3.5 API 可用性
- **非常容易获取**：注册 Anthropic Console 账户后即可创建 API Key。
- 需要绑定支付方式并充值 Credits（最低通常 $5 即可开始使用）。
- 支持通过 AWS Bedrock、Google Cloud Vertex AI 等云厂商间接调用（定价和限制可能不同）。

### 3.6 ToS 相关条款（商业条款）
> 来源：[Anthropic Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms)

关键限制摘要：
- **禁止转售（Resale）**："Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or **resell the Services except as expressly approved by Anthropic**..."
- **禁止反向工程**：不得反编译、反向工程、复制服务。
- **数据隐私**：商业条款下 Anthropic 不得使用 Customer Content 训练模型（默认 30 天保留，Enterprise 可协商 Zero Data Retention）。
- **用户责任**：客户需确保其最终用户遵守 Usage Policy。
- **Wrapper 模式风险**：禁止将 Anthropic API 作为纯代理（passthrough）向第三方提供。产品必须有实质性附加价值（如独有数据、工作流、自定义 UI 等）。
- **地区限制**：客户只能在 Anthropic 当前支持的国家和地区使用服务。

### 3.7 模型能力关键参数

| 能力 | 说明 |
|------|------|
| **上下文窗口** | 标准 200K tokens；Opus 4.6+ / Sonnet 4.6+ API 支持 1M tokens（beta） |
| **多模态** | 支持文本 + 图像输入（PDF、照片、图表）；不支持原生音频/视频 |
| **工具调用** | 支持 Function Calling、MCP Connectors、外部工具集成 |
| **推理模式** | Adaptive Thinking（自适应推理）：模型自行决定推理深度；支持 `standard` / `high` / `xhigh` / `max` 等级 |
| **代码能力** | 业内领先的编码能力，支持代码生成、重构、调试、代码执行 |
| **Prompt Caching** | 支持上下文缓存，降低重复调用成本（Write 约 1.25x 输入价，Read 仅 $0.10–$1/MTok） |
| **Batch Processing** | 异步批量处理，**50% 折扣** |
| **Structured Output** | 支持 JSON 模式等结构化输出 |
| **Streaming** | 支持 SSE 流式返回 |

### 3.8 支付方式
- **支持**：Visa、Mastercard、AmEx、主流借记卡、企业信用卡
- **不支持**：PayPal、Venmo、电汇（标准自助账户）、支付宝、微信支付、加密货币、预付礼品卡
- **企业客户**：可协商 ACH、发票/账期（Net terms）、AWS Marketplace 渠道付费
- **账单地址**：必须与银行卡记录严格匹配，跨境交易可能触发 3DS 验证

---

## 4. 额度与过期机制

### 4.1 订阅计划（Pro / Max）

| 项目 | 说明 |
|------|------|
| 计费周期 | 月付/年付，自动续费 |
| 未使用额度 | 滚动窗口内未用完的配额**不 rollover** |
| 退款 | **一般不退款**（部分司法管辖区 7 天例外） |
| 取消后 | 已付费周期结束前可继续使用 |
| 升级/降级 | 支持在周期内调整，按比例计费 |

### 4.2 API Credits（预付积分）

| 项目 | 说明 |
|------|------|
| 有效期 | 自**最近一次充值起 365 天** |
| 过期处理 | 自动清零，**不可恢复、不可退款** |
| 退款条件 | 充值后 24 小时内完全未使用，且未享受任何优惠/促销 |
| 退款手续费 | 扣除支付渠道费、汇率损失、5% 平台处理费（最低 $1） |
| 部分消费 | 已部分消费的积分**不可退未使用部分** |
| 账户关闭 | 剩余积分被没收 |
| 促销积分 | 可能适用更短有效期，以具体条款为准 |

> **社区争议**：2026 年 6 月有用户公开披露其 2025 年 6 月购买的 $24.60 API Credits 在一年后被过期清零，引发对 "付费积分却按游戏代币逻辑处理" 的批评。Anthropic 官方条款明确写明积分 "non-refundable, no cash value, expire after one calendar year"。

### 4.3 对比汇总

| 维度 | 订阅（Pro/Max） | API Credits |
|------|----------------|-------------|
| 费用模式 | 固定月费 | 预付积分 + 按量消耗 |
| 未使用额度 | 滚动窗口不 rollover | 365 天后过期清零 |
| 退款 | 一般不退 | 24 小时内未使用可退（扣手续费） |
| 超额使用 | Max 可按 API 价购买额外（政策曾暂停） | 达到月度上限后阻断 |
| 适合人群 | 个人日常用户、轻量开发者 | 开发者、企业、自动化/生产环境 |

---

## 5. ToS 与转售条款

### 5.1 消费者条款（Consumer Terms）—— 适用于 claude.ai / Pro / Max

> 来源：[Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms)

**核心禁止行为**：
1. **共享账号/凭证**：禁止分享登录信息、API Key、账户凭证；禁止将账户提供给他人。
2. **开发竞争产品**：禁止使用服务开发竞争产品，或训练竞争性 AI 模型。
3. **转售（Resell）**：禁止转售服务。
4. **自动化访问（非 API 途径）**：除非通过 Anthropic API Key，否则禁止通过 bot、script 等非人工方式访问 claude.ai。
5. **数据训练**：默认可使用用户对话训练模型（需手动 opt-out）。

### 5.2 商业条款（Commercial Terms）—— 适用于 API / Enterprise

> 来源：[Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)

**核心禁止行为**：
1. **转售限制**："Customer may not... resell the Services **except as expressly approved by Anthropic**."
2. **竞争限制**：禁止为构建竞争产品或服务而访问 API，包括训练竞争模型。
3. **反向工程**：禁止反编译、反向工程、复制服务。
4. **第三方责任**：客户必须确保其最终用户遵守 Usage Policy。
5. **Wrapper/Pure Relay 禁止**：禁止将 API 作为纯通道向第三方提供；产品必须有实质性附加价值（如独有数据、工作流、自定义功能等）。
6. **地区合规**：客户只能在 Anthropic 支持的国家/地区使用服务。

### 5.3 2026 年 1 月执行事件
- Anthropic 在 2026 年 1 月确认收紧技术保护措施，阻止第三方工具（如 OpenCode、某些 harness）**模拟/提取 Claude Code 的 OAuth token** 以绕过官方客户端使用订阅额度。
- 该行动被解读为打击 "subscription arbitrage"：$200/月的 Max 订阅通过自动化可消耗相当于 $1,000+/月 API 的 token 量，Anthropic 试图将高量自动化用户推向 API 按量计费。

### 5.4 合规建议
- **个人使用**：在 Pro/Max 订阅内通过官方 Claude Code CLI 使用是允许的；不要尝试提取 OAuth token 供第三方工具使用。
- **商业/生产使用**：必须使用 API Key 并遵守 Commercial Terms，避免 "wrapper" 架构风险。
- **多用户/团队**：Claude Team / Enterprise 计划提供合规的多用户管理；禁止通过共享单个 Pro/Max 账户来服务多人。

---

## 6. 模型能力关键参数

| 参数 | 详情 |
|------|------|
| **当前模型系列** | Fable 5（最新）、Opus 4.8、Sonnet 5、Haiku 4.5 |
| **上下文长度** | 标准 200K tokens；Opus 4.6+ / Sonnet 4.6+ API 支持 1M tokens（beta） |
| **知识截止** | Sonnet 5 约 2025 年 7 月；不同模型略有差异 |
| **多模态** | 文本 + 图像输入；不支持原生音频/视频 |
| **最大输出** | 标准 8,192 tokens；Opus 4.7 可达 128,000 tokens |
| **工具调用** | Function Calling、MCP Connectors、外部 API 集成 |
| **推理模式** | Adaptive Thinking（自动调整推理深度）；Extended Thinking（已逐步弃用） |
| **代码能力** | 顶级编码表现，Claude Code 为官方终端 AI 编程工具 |
| **Agent 能力** | 支持 Computer Use（屏幕操作）、多步骤工具调用、自主规划 |
| **Prompt Caching** | 支持，大幅降低重复上下文成本 |
| **Batch API** | 支持，异步批量处理享 50% 折扣 |
| **Web Search** | 内置搜索能力（API 和订阅版均可用） |
| **代码执行** | 沙箱化 Python 执行（50 小时/日/组织免费） |
| **结构化输出** | 支持 JSON 模式等 |

---

## 7. 支付方式与地区限制

### 7.1 支持方式

| 方式 | 支持？ | 备注 |
|------|--------|------|
| 信用卡（Visa/MC/AmEx） | ✅ | 主要支付方式 |
| 借记卡 | ✅ | 需支持在线支付 |
| 企业信用卡 | ✅ | 标准 |
| PayPal | ❌ | 不支持 |
| Venmo | ❌ | 不支持 |
| 电汇 | ❌（标准）/ ✅（Enterprise） | 自助账户不支持；企业可协商 |
| 支付宝 | ❌ | 不支持 |
| 微信支付 | ❌ | 不支持 |
| 加密货币 | ❌ | 不支持 |
| 预付礼品卡 | ❌ | 可能被拒绝 |
| iOS App Store | ✅（间接） | 通过 Apple 内购可绕过部分地区限制 |

### 7.2 地区限制
- Anthropic 仅向**特定国家/地区**提供 claude.ai 和 API 服务。
- 若所在地区不在支持列表，支付可能被拒绝，或访问被阻断。
- 部分用户通过**虚拟信用卡 + 稳定 IP** 尝试订阅，但存在账户被风控/暂停的风险。
- 通过 **AWS Bedrock**、**Google Vertex AI** 等云厂商渠道，可在更多地区间接使用 Claude 模型（计费走云厂商，不受 Anthropic 直接地区限制）。

### 7.3 账单与税务
- 显示的订阅价格通常不含税，结账时可能额外计算 VAT/GST。
- API Credits 充值时可能同时收取 VAT（如欧洲用户案例显示 $20 Credits + $4.60 VAT = $24.60）。
- 企业客户可申请发票，通过账单历史下载。

---

## 8. 总结与风险提示

### 8.1 定价总结

| 场景 | 推荐方案 | 预估月成本 |
|------|----------|-----------|
| 个人日常聊天 | Claude Pro（$20/月） | $20 |
| 个人高频使用（每天数小时） | Max 5x（$100/月）或 Max 20x（$200/月） | $100–$200 |
| 开发者/自动化/生产 | API + 按需积分 | $5–$200,000+ |
| 小型团队（5–150 人） | Team Standard（$25/座/月）或 Team Premium（$125/座/月） | 按人数计 |
| 大型企业 | Enterprise（定制，$20+/座 + API 使用费） | 定制 |

### 8.2 关键风险点
1. **额度不透明**：Pro/Max 的精确配额 Anthropic 不公开，实际使用体验因人而异。
2. **API Credits 过期**：预付积分 1 年过期且不可退，低频用户建议小额度多次充值。
3. **Wrapper/转售风险**：纯 API 代理模式已被 Anthropic 明确禁止，商业化产品需构建实质性附加价值。
4. **地区与支付风险**：部分地区不支持，跨境支付失败率高；建议确认账单地址与 IP 一致。
5. **数据训练默认**：Consumer 账户（Pro/Max）默认可能使用对话训练模型，敏感内容务必在设置中关闭 Data Usage。
6. **Agent SDK 政策变动**：2026 年 Anthropic 多次调整 Agent SDK 计费规则（计划从订阅池分离后又暂停），需持续关注官方公告。
7. **Rate Limit 频繁变动**：Anthropic 在 2026 年多次调整 tier 结构和限额，生产系统需做好动态适配和熔断机制。

### 8.3 信息未确认项
- 以下信息未找到官方公开明确说明，标注为 **"未找到公开信息"**：
  - Pro/Max 订阅的**精确 token 数/消息数上限**（Anthropic 刻意不公开）。
  - 特定国家/地区的**完整支持列表**（官网仅提示 "certain regions"）。
  - **教育/学术折扣**的具体额度（仅提到有机构级计划，无个人学生折扣公开信息）。
  - **API Credits 到期前的提醒机制**（条款提到可能发邮件，但无具体频率/提前天数）。

---

> **报告结束**。如需进一步调研其他平台（如 OpenAI、Google Gemini、Kimi、DeepSeek 等），可继续补充。
