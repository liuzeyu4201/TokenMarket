# AI 平台市场调研报告：GitHub Copilot + Perplexity + xAI Grok

> **调研日期**：2026-07-10  
> **分析师**：AI 市场调研子代理  
> **数据来源**：官方文档、第三方评测、行业博客、API 定价页面（通过 kimi_search_v2 / kimi_fetch_v2 采集）  
> **免责声明**：AI 平台定价与政策变化频繁，本报告基于公开可检索信息编制，具体以各平台官方最新页面为准。

---

## 目录

1. [GitHub Copilot](#1-github-copilot)
2. [Perplexity](#2-perplexity)
3. [xAI Grok](#3-xai-grok)
4. [横向对比速查表](#4-横向对比速查表)

---

## 1. GitHub Copilot

### 1.1 平台名称与套餐概览

GitHub Copilot 是 GitHub（Microsoft 旗下）推出的 AI 编程助手，直接集成在 VS Code、JetBrains、Visual Studio、Neovim 等 IDE 中，提供代码补全、Chat、Agent 模式、代码审查等功能。

| 套餐名称 | 目标受众 | 月费（USD） | 年费（USD） |
|---------|---------|------------|------------|
| **Copilot Free** | 个人（轻量） | $0 | — |
| **Copilot Pro** | 个人开发者 | $10 | $100 |
| **Copilot Pro+** | 个人重度用户 | $39 | $390 |
| **Copilot Max** | 个人专业用户 | $100 | — |
| **Copilot Business** | 团队/组织 | $19/用户 | — |
| **Copilot Enterprise** | 大型企业 | $39/用户 | — |

> 注：2026 年 6 月 1 日起，GitHub Copilot 全面从“Premium Request Units (PRU)”计费模式切换为 **AI Credits** 按量计费模式。1 Credit = $0.01 USD。

---

### 1.2 定价详情（月费 / 年费 / 按量付费）

- **基础订阅费**：上表所列月费/年费保持不变，不因新计费模式而改变。
- **按量计费（超出额度）**：超出月度 AI Credits 额度后，按各模型对应的 token 费率计费（详见 1.3）。
- **Legacy 超额费（旧版 PRU 制）**：在 2025 年中 PRU 时代，超额 Premium Request 按 **$0.04/条** 计费。此费率已随 2026-06-01 的 Credits 切换而失效，但年度订阅用户在到期前仍沿用旧体系。
- **Copilot 代码审查**：除消耗 AI Credits 外，还同时消耗 GitHub Actions 分钟数，按现有 GitHub Actions 分钟费率计费。

---

### 1.3 Token 额度与调用限制

自 2026-06-01 起，各套餐包含的 **AI Credits** 额度如下：

| 套餐 | 月度 AI Credits | 构成说明 | 代码补全 |
|------|----------------|---------|---------|
| **Free** | 有限免费额度 | 轻量配额 | 2,000 次/月 |
| **Pro** | 1,500 Credits | 1,000 base + 500 flex | 无限 |
| **Pro+** | 7,000 Credits | 3,900 base + 3,100 flex | 无限 |
| **Max** | 20,000 Credits | 10,000 base + 10,000 flex | 无限 |
| **Business** | 1,900/用户 | 标准额度（2026-06~08 促销期为 3,000） | 无限 |
| **Enterprise** | 3,900/用户 | 标准额度（2026-06~08 促销期为 7,000） | 无限 |

> **Flex Credits**：GitHub 声明 flex 额度是“额外可变配额”，会随着模型定价与效率变化调整，优先消耗 base credits，再自动消耗 flex credits。
> 
> **组织池化**：Business / Enterprise 的 Credits 在账单实体层级共享（如 100 人的 Business 组织共享 190,000 Credits），而非按个人账户隔离。

#### Legacy PRU 制（年度订阅用户在到期前仍适用）

| 套餐 | 月度 Premium Requests |
|------|----------------------|
| Free | 50 PRU + 2,000 补全 |
| Pro | 300 PRU |
| Pro+ | 1,500 PRU |
| Business | 300 PRU/用户 |
| Enterprise | 1,000 PRU/用户 |

**模型倍率（Legacy 年度订阅者）**：不同模型消耗 PRU 的倍率不同。例如：
- GPT-4o / GPT-4o mini / GPT-5 mini：0.33×
- GPT-5.1：3×
- Claude Sonnet 4.6：9×
- Claude Opus 4.7 / 4.8：27×
- Copilot 代码审查：13×（2026-06-01 起）
- Auto 模型选择：享受 10% 折扣（0.9× 倍率）

---

### 1.4 过期机制（Rollover / 退款）

- **AI Credits**：月度 credits 在每月 1 日 00:00 UTC 重置。**未使用额度不 rollover**，不累积至下月。
- **Legacy PRU**：同上，未使用 Premium Requests 在每月 1 日重置，不结转。
- **退款**：年度订阅在到期前可转换至月度计划，GitHub 会按比例提供 prorated credits。取消订阅后，当前计费周期结束前仍可继续使用。
- **余额可退**：未找到公开信息明确说明充值余额可退。

---

### 1.5 API 可用性

- **Copilot API Key**：GitHub Copilot 本身不直接提供“个人 API Key”供外部调用。消费主要通过 IDE 扩展和 GitHub.com 界面使用。
- **GitHub Models**：GitHub 提供 GitHub Models（Marketplace）用于学习、试用和测试 AI 模型，但受限于模型提供方条款。
- **Enterprise BYOK（Bring Your Own Key）**：2025-11-20 起，Enterprise 用户可在公共预览中使用 BYOK，将自有 Azure OpenAI / OpenAI API Key 与 Copilot 组织管理整合，但仍需按 Copilot 席位付费。
- **第三方 API 封装**：GitHub 官方未提供独立的 Copilot 外部 REST API；任何第三方声称“Copilot API”的通常是逆向或代理，存在 ToS 风险。

---

### 1.6 ToS 相关条款（账号共享 / 转售 / Sublicensing）

- **GitHub Copilot Product Specific Terms**（2023-09-27 版，后被 2026-03-05 更新的 Generative AI Services Terms 取代）明确：
  - “Your use of GitHub Copilot is subject to the Acceptable Use Policies.”
  - 禁止将 Copilot 用于生成非法或侵犯他人权利的代码建议。
  - 建议开启 Duplicate Detection 过滤，否则 GitHub 的第三方索赔辩护义务可能失效。
- **GitHub 主服务条款**：账号共享（seat sharing）在组织计划中被明确限制——按“席位（seat）”授权，Billing 周期内移除席位仍计费至周期结束。同一用户跨多个组织时仅计费一次。
- **转售 / Sublicensing**：未找到公开文本明确允许 sublicense。GitHub 的“Additional Products and Features”条款对 Actions、Codespaces 等明确禁止“resell or provide as a standalone service”，Copilot 受 Acceptable Use Policies 约束，可推断禁止以转售或 API 代理形式提供。
- **IP 赔偿**：Business / Enterprise 提供 IP 赔偿（Indemnity），但要求开启 Duplicate Detection 过滤为 Block 模式。

---

### 1.7 模型能力关键参数

| 能力 | 说明 |
|------|------|
| **上下文长度** | 随模型而异；Pro+ 与 Enterprise 提供更长上下文窗口。GPT-4o / Claude 3.5 Sonnet 等级别模型上下文在 128K–256K 范围。 |
| **多模态** | 支持图像输入（Copilot Chat 可分析截图、图表）。 |
| **推理/代码** | 核心能力为代码补全、多文件编辑、代码审查、Agent 模式（自主任务执行）。 |
| **工具调用** | Agent 模式支持 tool calls，可执行终端命令、读写文件、调用外部工具（在 IDE 内）。 |
| **支持模型** | GPT-4o、GPT-5 系列、Claude 3.5/4 Sonnet、Claude Opus、Gemini 系列（不同套餐模型权限不同；高阶模型限制在 Pro+/Enterprise/Max）。 |
| **代码补全** | 所有付费套餐均包含**无限**代码补全（inline suggestions / Next Edit），不计入 Credits。 |

---

### 1.8 支付方式与地区限制

| 项目 | 说明 |
|------|------|
| **支持卡组织** | Visa、Mastercard、American Express（国际信用卡/借记卡）。 |
| **PayPal** | 部分国家可用。 |
| **国内用户** | 中国大陆信用卡/借记卡直接支付成功率低；常见方案为虚拟 Visa 卡（如 wise、fome、Depay 等）或 PayPal 绑定国际卡。 |
| **货币** | 以 USD 结算。 |
| **地区限制** | 未找到明确国家/地区封锁列表，但受美国出口管制（OFAC）约束，受制裁国家可能无法使用。 |

---

## 2. Perplexity

### 2.1 平台名称与套餐概览

Perplexity 是 AI 原生搜索引擎，以实时联网搜索、引用来源（citations）和深度研究（Deep Research）为核心特色。提供消费级和企业级订阅。

| 套餐名称 | 目标受众 | 月费（USD） | 年费（USD） |
|---------|---------|------------|------------|
| **Free** | 个人（轻量） | $0 | — |
| **Pro** | 个人重度用户 | $20 | $200（省 17%） |
| **Max** | 个人专业/研究者 | $200 | — |
| **Enterprise Pro** | 团队/企业 | $40/用户 | $400/用户 |
| **Enterprise Max** | 数据密集型组织 | $325/用户 | — |

> 注：2025 年曾出现 $50/月的 Max 计划说法，但当前主流公开信息显示 Max 为 $200/月。以官方 perplexity.ai 为准。

---

### 2.2 定价详情（月费 / 年费 / 按量付费）

- **Pro / Max**：固定订阅制，无额外月费（在聊天界面内）。
- **API**：完全独立于消费订阅，采用 **Prepaid Credits**（预付费额度）制，按 token 与搜索深度计费。
  - Pro 订阅者每月额外获得 **$5 API Credits**，但远不足以覆盖生产级调用。
  - 重度使用需自行在 API 后台充值购买 credits。
- **Enterprise**：高用量可谈判定制价格（Volume-based contracts）。

---

### 2.3 Token 额度与调用限制

#### 消费端（网页/APP）查询限制

| 套餐 | 每日 Pro Searches | 文件上传 | 其他说明 |
|------|------------------|---------|---------|
| **Free** | 5 次/日 | 3 文件/日 | 无限基本搜索（标准模型） |
| **Pro** | 300+ 次/日 | 无限 | 可使用 GPT-4、Claude 3 等高级模型；午夜 UTC 重置 |
| **Max** | 无限 | 无限 | 无限 Labs 使用；高峰时段优先处理 |
| **Enterprise Pro** | 300+ 次/用户/日 | 无限 | 团队管理、内部知识搜索 |
| **Enterprise Max** | 无限 | 无限 | 无限 Labs、最新模型、组织级文件库 |

> 注：Pro 的 300+ 为“约数”，实际上限可能根据流量动态调整。

#### API 端限制

| 项目 | 说明 |
|------|------|
| **新账户 Rate Limit** | 20–50 RPM（Requests Per Minute） |
| **自动升级** | 随着月度消费金额提升，RPM 自动上调 |
| **Tier 1（$0–$50）** | 基础限制 |
| **Enterprise** | 可协商 unlimited + SLA |
| **Spend Caps** | 控制台支持设置实时花费上限 |

#### API Credits 用量参考

| 场景 | 估计可执行次数（$5 Credits） |
|------|---------------------------|
| Sonar Pro + High Depth | ~250 次查询 |
| Standard Sonar + Low Depth | ~1,250 次查询 |
| 典型生产需求 | 5,000+ 次/月（需额外充值） |

---

### 2.4 过期机制（Rollover / 退款）

- **Pro 订阅 API Credits**：每月固定发放 $5 API Credits，**未找到公开信息**说明是否 rollover。按行业惯例，月度发放额度通常月底清零，不累积。
- **Prepaid API Credits**：未找到明确的 rollover 政策；按大多数 SaaS 惯例，预付费 credits 通常不过期，但需以官方为准。
- **订阅退款**：未找到公开退款政策；按常见 SaaS 做法，按比例退款可能仅在特定情形下（如购买错误）提供。
- **取消**：可随时取消，当前周期结束前继续使用。

---

### 2.5 API 可用性

- **API Key**：易于获取。
  1. 注册 perplexity.ai 账号
  2. 进入 Settings → API
  3. 添加支付方式（即使免费用户也需绑卡才能启用 API）
  4. 即时生成 API Key，无需审批等待
- **OpenAI 兼容**：API 端点与 OpenAI SDK 格式兼容，仅需修改 `base_url` 为 `https://api.perplexity.ai` 并替换 Key 前缀 `pplx-`。
- **模型家族**：Sonar（轻量）、Sonar Pro（深度搜索）、Sonar Reasoning Pro（推理+搜索）、Sonar Deep Research（多步研究）等。
- **Search API**：2025-09 推出独立 Search API，返回原始搜索片段与元数据，适合自建 RAG。

---

### 2.6 ToS 相关条款（账号共享 / 转售 / Sublicensing）

- **Perplexity Terms of Service**：未能通过 fetch 直接获取完整文本（网络错误），但第三方汇总显示：
  - 账户应在个人或组织授权范围内使用；Enterprise 计划明确按 seat 授权。
  - **未找到**明确禁止账号共享的条文原文，但“per user”定价结构暗示不可跨用户共享。
  - **API Key**：API 文档提示用户须保密 API Key，不共享给第三方。所有 Key 下的活动由账户持有人负责。
  - **转售**：未找到明确禁止转售 API 额度的条文；但按 Stripe 订阅与 API credits 的通用 SaaS 逻辑，未经授权的批量转售或 sublicense 极可能违反 ToS。
  - **Enterprise 数据承诺**：Perplexity 承诺 Enterprise 客户数据**永不用于模型训练**（SOC 2 合规）。

---

### 2.7 模型能力关键参数

| 能力 | 说明 |
|------|------|
| **上下文长度** | 随底层模型而异（GPT-4 / Claude 3 系列均支持 128K+ 上下文）。 |
| **实时搜索** | 所有查询默认联网，返回带来源链接的引用（citations）。 |
| **多模态** | 支持文件上传（PDF、CSV、图片）进行分析；Pro 以上支持图像生成（DALL-E 3 等）。 |
| **推理/代码** | 支持多步推理（Pro Search）、代码解释、数据分析；Max 支持 Deep Research 任务。 |
| **工具调用** | 消费端通过界面自动选择搜索工具；API 端可配置 `search_parameters` 控制搜索行为。 |
| **Labs** | Max / Enterprise Max 可访问 Perplexity Labs，用于构建仪表盘、应用等。 |

---

### 2.8 支付方式与地区限制

| 项目 | 说明 |
|------|------|
| **支持卡组织** | 信用卡（Visa、Mastercard、Amex 等）；通过 Stripe 处理。 |
| **PayPal** | 支持；2025 黑五曾推出 PayPal 专属折扣。 |
| **PayPal Pay Later** | 支持分期付款。 |
| **Enterprise** | 支持银行转账、wire transfer、invoice billing。 |
| **地区敏感性** | 订阅 credits 需与账号注册国家匹配，存在区域定价/风控限制。 |
| **国内用户** | 中国大陆用户可用国际信用卡或虚拟卡通过 Stripe 支付；未找到明确地区封锁。 |
| **货币** | 以 USD 结算。 |

---

## 3. xAI Grok

### 3.1 平台名称与套餐概览

Grok 是 Elon Musk 旗下 xAI 开发的对话式 AI，与 X（原 Twitter）深度集成，强调实时 X 数据访问、幽默风格和“Truth-seeking”定位。2025 年底起推出独立订阅体系。

| 套餐名称 | 目标受众 | 月费（USD） | 年费（USD） | 说明 |
|---------|---------|------------|------------|------|
| **Free** | 个人尝鲜 | $0 | — | grok.com 或 X 内使用 |
| **X Premium** | X 平台用户 | $8 | $84 | 附带基础 Grok 访问 |
| **SuperGrok Lite** | 轻量付费用户 | $10 | — | 2026-03-25 推出 |
| **SuperGrok** | 个人主力用户 | $30 | $300（省 17%） | 独立 AI 订阅，全功能 |
| **X Premium+** | X 重度用户 | $40 | $395 | 含 Grok + 无广告 X |
| **SuperGrok Heavy** | 专业/研究者 | $300 | — | 最高优先级、完整 Grok 4.3 |
| **Grok Business** | 团队/企业 | $30/用户 | — | 团队工作区、集中计费 |
| **Enterprise** | 大型组织 | 定制 | — | 无限用户、SSO、审计日志 |

> **重要**：Grok 的**消费订阅**与 **API** 是完全独立的计费轨道。订阅 SuperGrok / X Premium 不会获得 API 额度，反之亦然。

---

### 3.2 定价详情（月费 / 年费 / 按量付费）

#### 消费订阅
- 如上表所示，按固定月费/年费计费。
- **SuperGrok Heavy**：$300/月，是目前唯一**确认始终可用** Grok 4.3 的消费者套餐。
- **SuperGrok / X Premium+**：Grok 4.3 采用分阶段（staged rollout）推送，非所有用户随时可用。
- **Free 周末活动**：自 2025-05 起，每周五 00:00 UTC 至下周一 08:00 UTC，免费用户可临时获得高级功能（Grok 4 扩展推理、5× 请求上限）。

#### API 按量计费（Pay-as-you-go）

| 模型 | Input $/1M tokens | Cached Input $/1M | Output $/1M | 上下文窗口 |
|------|------------------|------------------|-------------|-----------|
| **grok-4.3**（旗舰） | $1.25 | $0.20 | $2.50 | 1M |
| **grok-4.20-multi-agent** | $1.25 | $0.20 | $2.50 | 2M |
| **grok-4.20-reasoning** | $1.25 | $0.20 | $2.50 | 1M |
| **grok-4.20-non-reasoning** | $1.25 | $0.20 | $2.50 | 1M |
| **grok-build-0.1**（编程） | $1.00 | $0.20 | $2.00 | 256K |
| ~~grok-4~~ | ~~$3.00~~ | ~~$0.75~~ | ~~$15.00~~ | ~~256K~~ |
| ~~grok-4.1-fast~~ | ~~$0.20~~ | ~~$0.05~~ | ~~$0.50~~ | ~~2M~~ |
| ~~grok-3~~ | ~~$3.00~~ | ~~$0.75~~ | ~~$15.00~~ | ~~131K~~ |

> **2026-05-15 退役通知**：grok-4、grok-4-fast、grok-4.1、grok-4.1-fast、grok-code-fast-1、grok-3 等旧模型 ID 已退役。调用这些旧 ID 不会报错，而是**静默重定向至 grok-4.3**，并按 grok-4.3 的 $1.25/$2.50 计费。旧代码中 pinned 的低价模型必须更新，否则成本大幅上升。

#### API 工具附加费（与 token 分开计费）

| 工具 | 费率 |
|------|------|
| Web Search | $5.00 / 1,000 次 |
| X Search | $5.00 / 1,000 次 |
| Code Execution | $5.00 / 1,000 次 |
| File Attachments | $10.00 / 1,000 次 |
| Collections (RAG) Search | $2.50 / 1,000 次 |
| 图像/视频理解 | 按 token 计费 |
| Realtime Voice | $0.05 / 分钟 |
| Text-to-Speech | $15.00 / 1M 字符 |
| Speech-to-Text (REST) | $0.10 / 小时 |
| Speech-to-Text (Streaming) | $0.20 / 小时 |

#### 存储费用

- File Storage：$0.025 / GiB / 天
- Collection Storage：$0.10 / GiB / 天
- Downloads：$0.20 / GiB

#### Batch API 折扣
- 异步处理（24 小时窗口内）享受 **20–50% 折扣**，具体依模型而异。

---

### 3.3 Token 额度与调用限制

#### 消费端（grok.com / X App）

| 套餐 | 大致请求限制 | 上下文窗口 | 可用模型 |
|------|-------------|-----------|---------|
| **Free** | ~10 次 / 2 小时 | 有限 | 基础 Grok 4 / 4.1（有限） |
| **SuperGrok Lite** | 比 Free 2× 更长对话 | 有限 | Grok 3.5、Grok Imagine |
| **SuperGrok** | ~100 次 / 2 小时 | 128K | Grok 4、Grok 4.1、DeepSearch、Big Brain、Voice |
| **SuperGrok Heavy** | 最高优先级 | 256K–428K | Grok 4 Heavy、16-agent 并行、完整 Grok 4.3 |
| **X Premium** | X 内基础访问 | 有限 | 基础 Grok |
| **X Premium+** | X 内更高吞吐 | 有限 | Grok 4（分阶段推送 4.3） |
| **Grok Business** | 与 SuperGrok 相同 | 128K | 团队管理功能 |

> 注：消费端请求限制为“每 2 小时窗口”动态限流，非严格硬顶，高峰期可能更严格。

#### API 端
- 无固定月度额度，纯按量计费。
- **新账号促销**：
  - 注册即送 **$25 试用 credits**（30 天内有效，不结转）。
  - 数据共享计划（Data Sharing Program）：开启“Share API Inputs for Model Training”后，曾提供额外 **$150/月** 免费 credits。但该项目已多次变更，**需在当前 xAI Console 中核实可用性**。
- **Spend Controls**：
  - Hard monthly cap（硬上限，超出后拒绝请求）
  - 用量提醒：50%、75%、90%
  - Auto-recharge（可选，方便但风险较高）

---

### 3.4 过期机制（Rollover / 退款）

- **$25 促销 credits**：注册后 30 天内有效，**过期不 rollover**。
- **数据共享 credits**：按月刷新，未找到明确的 rollover 说明；通常按自然月重置。
- **消费订阅**：月度/年度订阅，取消后当前周期结束前继续可用；未找到退款政策公开信息。
- **API 余额**：按预付费/后付费模式，无固定过期机制，但需以官方账单为准。

---

### 3.5 API 可用性

- **获取方式**：极易获取。
  1. 访问 [console.x.ai](https://console.x.ai)
  2. 使用邮箱、X 账号或 Google 账号注册
  3. 完成手机与身份验证
  4. 进入 API → Manage API keys → 生成 Key
  5. 添加支付方式（信用卡）
- **OpenAI 兼容**：API 端点 `https://api.x.ai/v1`，请求格式与 OpenAI SDK 完全一致，可直接将 `base_url` 指向 xAI 即可。
- **区域端点**：支持 `us-east-1` 和 `eu-west-1`，可配置 `region` 满足数据驻留要求。全球端点自动路由。

---

### 3.6 ToS 相关条款（账号共享 / 转售 / Sublicensing）

- **xAI Terms of Service**：未能通过 fetch 直接获取完整文本（网络错误），但综合多个信源：
  - 消费订阅（SuperGrok / X Premium）按个人账户授权；**未找到**明确允许账号共享的条款。
  - **API Key**：API 文档要求保密，账户持有人对 Key 下的所有活动负责。禁止将 API Key 嵌入公开客户端或共享给第三方。
  - **数据训练**：
    - Free 及消费者计划：xAI **可能**使用对话数据改进模型。
    - Business / Enterprise：明确承诺**数据不用于训练**。
  - **违规费用**：Responses API 中，若请求违反使用政策并在生成前被拦截，收取 **$0.05/次**；若生成过程中被拦截，则收取正常生成费用 + 违规费。
  - **转售 / Sublicensing**：未找到明确条文，但 API 的“no minimum commitment, no monthly subscription”模式属于典型 SaaS 按量计费，按行业惯例禁止将 API 封装后以独立服务转售（reselling）或 sublicense。
  - **出口管制**：受美国标准出口管制约束，受制裁国家（如俄罗斯、伊朗、朝鲜等）无法使用。

---

### 3.7 模型能力关键参数

| 能力 | 说明 |
|------|------|
| **上下文长度** | grok-4.3 / grok-4.20 系列：1M–2M tokens；SuperGrok Heavy：256K–428K（消费端）。 |
| **实时 X 数据** | 核心差异化能力，可访问 X 平台实时趋势与讨论。 |
| **多模态** | Grok Imagine（图像/视频生成）、语音输入、Aurora 图像模型；SuperGrok Lite 支持 480p 视频生成。 |
| **推理/代码** | Grok 4 系列为推理优化模型；grok-build-0.1 为专用编程 Agent（支持 8 并行 sub-agents）。 |
| **工具调用** | API 支持 Web Search、X Search、Code Execution、File Attachments 等内置工具，按调用次数计费。 |
| **DeepSearch** | SuperGrok 以上支持 DeepSearch（多轮搜索+推理）；Big Brain Mode 为深度推理模式。 |
| **Agent 能力** | Grok Build（CLI Agent）支持多 worktree 并行、MCP 工具连接、自主任务执行。 |

---

### 3.8 支付方式与地区限制

| 项目 | 说明 |
|------|------|
| **支持卡组织** | 信用卡（Visa、Mastercard、Amex） via xAI Console / Stripe。 |
| **国内用户** | 中国大陆直接访问 grok.com / console.x.ai 需要 VPN/代理；支付需使用国际信用卡或虚拟卡。 |
| **制裁国家** | 俄罗斯、伊朗、朝鲜等受美国制裁司法管辖区明确无法使用。 |
| **EU / UK** | 无 GDPR 专项限制；xAI 持有 SOC 2 Type 2、GDPR、CCPA 认证。 |
| **Azure 备选** | Microsoft Azure AI Foundry 提供 Grok 企业部署（面向已有 Azure 关系的企业），为受限地区提供替代通道。 |
| **货币** | 以 USD 结算。 |
| **促销信用** | 新账号 $25 试用 credits（30 天有效）；数据共享计划最高 $150/月（需核实）。 |

---

## 4. 横向对比速查表

| 维度 | GitHub Copilot | Perplexity | xAI Grok |
|------|---------------|-----------|---------|
| **最低月费** | $0（Free） | $0（Free） | $0（Free） |
| **主力个人月费** | $10（Pro） | $20（Pro） | $30（SuperGrok） |
| **高端个人月费** | $39（Pro+） | $200（Max） | $300（SuperGrok Heavy） |
| **团队起步月费** | $19/用户（Business） | $40/用户（Enterprise Pro） | $30/用户（Grok Business） |
| **计费模式** | 订阅 + AI Credits 按量 | 订阅 + API 预付费 Credits | 订阅 + API 纯按量 |
| **月度额度** | 1,500–20,000 Credits 或无限补全 | Pro 搜索 300+/日；API $5/月（Pro） | 消费端 ~100 次/2h；API 无固定额度 |
| **额度 Rollover** | 否（月底重置） | 未找到明确信息 | 促销 $25 不 rollover |
| **API 获取难度** | 难（无个人独立 API；Enterprise BYOK 预览） | 极易（注册+绑卡即发） | 极易（注册+验证即发） |
| **API 兼容性** | 无标准 REST API（IDE 扩展） | OpenAI 兼容 | OpenAI 兼容 |
| **上下文上限** | 128K–256K（依模型） | 128K+（依底层模型） | 1M–2M（API）；256K–428K（消费端） |
| **核心特色** | IDE 内代码补全、Agent 编码 | 实时联网搜索、引用来源 | 实时 X 数据、幽默风格、超大上下文 |
| **多模态** | 图像输入（代码相关） | 文件上传、图像生成 | 图像/视频生成、语音 |
| **IP 赔偿** | Business/Enterprise 提供 | 未明确 | 未明确 |
| **数据训练政策** | 依 Telemetry 设置；Enterprise 可控 | Enterprise 永不用于训练 | Business/Enterprise 不用于训练 |
| **退款政策** | 年度转月度按比例 | 未找到公开信息 | 未找到公开信息 |
| **国内支付** | 需国际卡/虚拟卡 | 需国际卡/虚拟卡 | 需国际卡/虚拟卡 + VPN |
| **制裁地区** | 遵循美国出口管制 | 未明确 | 明确封锁 |

---

## 附录：信息置信度标注

| 信息类别 | 置信度 | 说明 |
|---------|-------|------|
| GitHub Copilot 定价与 Credits | ⭐⭐⭐⭐⭐ | 来自 GitHub 官方博客 2026-04-27 及多个 2026-06 更新信源 |
| GitHub Copilot 模型倍率 | ⭐⭐⭐⭐⭐ | 来自 docs.github.com 及 samexpert.com 2026-02 |
| GitHub Copilot ToS 摘录 | ⭐⭐⭐⭐ | 来自 GitHub 官方 PDF 条款（2023 版），2026-03 已被新 Generative AI Terms 取代，但核心原则不变 |
| Perplexity 定价与搜索限制 | ⭐⭐⭐⭐⭐ | 来自多个 2025-08 ~ 2025-12 信源，高度一致 |
| Perplexity API 机制 | ⭐⭐⭐⭐⭐ | 来自 techboosted.co.uk 2025-11 及 GlobalGPT 2025-12 |
| Perplexity ToS 细节 | ⭐⭐⭐ | 未能 fetch 到完整官方 ToS，依赖第三方摘要 |
| Grok 消费端定价 | ⭐⭐⭐⭐⭐ | 来自 techjacksolutions.com 2026-07、suprmind.ai 2026-05，均引用 xAI 官方 |
| Grok API 定价与模型退役 | ⭐⭐⭐⭐⭐ | 来自 mem0.ai 2026-06、suprmind.ai 2026-05，明确引用 xAI 官方 docs.x.ai |
| Grok API 工具费 | ⭐⭐⭐⭐⭐ | 同上，2026-05-07 数据 |
| Grok 数据共享/促销 Credits | ⭐⭐⭐⭐ | 存在变更历史，官方 Console 中需实时确认 |
| Grok ToS 细节 | ⭐⭐⭐ | 未能 fetch 到完整官方 xAI Terms，依赖第三方摘要 |
| 支付方式与地区 | ⭐⭐⭐⭐ | 基于多个中文/英文社区实测反馈汇总 |

---

> **报告结束**。如需对特定平台的某一维度进行深度挖掘，或需要实时抓取官网最新页面进行验证，请告知进一步指令。
