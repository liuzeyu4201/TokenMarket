# Google AI 平台调研报告

> **调研日期**: 2026-07-10  
> **调研目标**: Google Gemini 系列产品的定价、额度、API可用性、ToS条款及模型能力  
> **覆盖范围**: Gemini Advanced（消费订阅）/ Google AI Studio（开发者免费层）/ Vertex AI（企业API）/ Gemini API（按量计费）

---

## 目录

1. [Gemini Advanced（消费订阅层）](#1-gemini-advanced消费订阅层)
2. [Google AI Studio（开发者免费层）](#2-google-ai-studio开发者免费层)
3. [Gemini API（按量付费）](#3-gemini-api按量付费)
4. [Vertex AI（企业级托管）](#4-vertex-ai企业级托管)
5. [模型能力关键参数](#5-模型能力关键参数)
6. [ToS 与政策条款](#6-tos-与政策条款)
7. [支付方式与地区限制](#7-支付方式与地区限制)
8. [总结对比表](#8-总结对比表)

---

## 1. Gemini Advanced（消费订阅层）

### 1.1 平台名称与套餐

Google 在 2026 年 I/O 大会后重新命名了消费端订阅体系：

| 套餐名称 | 月费（USD） | 核心定位 |
|---------|------------|---------|
| **Google AI Plus** | $7.99/月 | 入门级，128K 上下文，200 GB 存储 |
| **Google AI Pro**（原 Gemini Advanced） | $19.99/月 | 主力套餐，1M 上下文，Gemini 3.1 Pro |
| **Google AI Ultra** | $99.99/月（I/O 2026 从 $249.99 降价） | 高用量，5x Pro 限额，20 TB 存储 |
| **Google AI Ultra 高级** | $200/月 | 最高限额，20x Pro 限额 |

> **促销优惠**：新用户通常可享受前几个月 50% 折扣（前两个月半价或首年半价）。

### 1.2 定价

- **月费**: 如上表所示，均为订阅制，按月扣费。
- **年费选项**: 未找到公开的年费折扣信息，目前仅支持月付。
- **额外费用**: 无额外按量费用，但 AI 生成 credits（如 Flow、Whisk 等）有月度配额限制。

### 1.3 Token 额度与调用限制

Google 在 2026 年已从固定消息/请求数限额改为 **compute-based usage limits**（基于计算量的动态限额）：

| 套餐 | 上下文窗口 | 存储 | AI Credits（月度） | 限额特点 |
|-----|-----------|------|------------------|---------|
| Free | 128K–200K | 15 GB | 无 | 基础模型，无优先权 |
| Plus | 128K | 200 GB | 200 | 日常轻度使用 |
| Pro | **1M tokens** | 5 TB | 1,000 |  generous compute limits |
| Ultra | 1M tokens | 20 TB | 5x Pro | 更高限额，优先体验新功能 |

> **关键变化**：Google 不再公开披露固定的每日消息数量，而是采用基于计算资源的弹性限额。高峰时段可能受到 soft limits 约束。

### 1.4 过期机制

- **订阅周期**：按月计费，订阅额度每月重置。
- **Rollover**：**未找到**月度未使用额度（如 AI credits）可累积至下月的公开说明。通常此类订阅制服务不累积未使用额度。
- **退款**：Google 的订阅退款政策取决于购买渠道（Google Play/App Store）和所在地区。通常已开始计费的周期不予退款，但可在当前周期结束前取消续订。
- **充值余额**：不适用（非预充值模式）。

### 1.5 API 可用性

- **不提供直接的 API Key**。Gemini Advanced 是面向终端消费者的聊天产品，通过 gemini.google.com 或移动 App 访问。
- 开发者需使用 **Google AI Studio** 或 **Vertex AI** 获取 API 访问。

### 1.6 模型能力关键参数

| 参数 | 说明 |
|-----|------|
| 默认模型 | Gemini 3.5 Flash（免费用户）；Gemini 3.1 Pro（Pro/Ultra 订阅者） |
| 上下文窗口 | 最高 1M tokens（Pro/Ultra） |
| 多模态 | 支持文本、图像、视频、音频输入；支持图像生成（Nano Banana） |
| 推理能力 | Gemini 3.1 Pro 为旗舰推理模型；Ultra 含 Deep Think 模式 |
| 代码能力 | 集成 Gemini Code Assist（Pro/Ultra 含部分配额） |
| 工具调用 | 支持（需通过 API 层使用） |
| 视频分析 | 支持（通过 Omni 视频功能，Ultra 套餐） |

### 1.7 支付方式与地区

- 支持 Google Play / Apple App Store 内购，或网页端绑定信用卡。
- 全球大多数主流市场均已上线（2026 年 1 月起全球推广）。
- 部分地区可能因当地法规限制可用性。

---

## 2. Google AI Studio（开发者免费层）

### 2.1 平台名称与套餐

- **平台名称**: Google AI Studio（aistudio.google.com）
- **套餐**: 免费层（Free Tier），无需信用卡，注册 Google 账号即可使用。

### 2.2 定价

- **完全免费**。无需绑定支付方式即可获取 API Key 并调用。
- 免费层存在严格速率限制，超出后需升级至付费层（绑定 Cloud Billing 账号）。

### 2.3 Token 额度与调用限制

免费层速率限制（Rate Limits）按模型维度划分。注意：**Google 在 2025 年 12 月 7 日大幅削减了免费层配额**，以下为 2026 年中实际执行的常见限制（以 Google AI Studio 界面实时显示为准）：

| 模型 | RPM（请求/分钟） | TPM（Token/分钟） | RPD（请求/天） | 说明 |
|-----|----------------|------------------|---------------|------|
| **Gemini 3.5 Flash** | ~10 | ~250,000 | ~1,500 | 2026 年 5 月新模型 |
| **Gemini 3.1 Flash-Lite** | ~15 | ~250,000 | ~1,000–1,500 | 3 系列最便宜 |
| **Gemini 3 Flash** | ~10 | ~250,000 | ~1,500 |  |
| **Gemini 2.5 Flash** | ~10 | ~250,000 | ~250 | 较旧但仍可用 |
| **Gemini 2.5 Flash-Lite** | ~15–30 | ~250,000–1,000,000 | ~1,000–1,500 | 最高免费限额 |
| **Gemini 2.5 Pro** | ~5 | 有限 | ~50–100 | 仅 Trial 级别 |
| **Gemini 2.0 Flash** | ~10–15 | ~250,000–1,000,000 | ~200–250 | 含 1M 上下文 |
| **Gemini 1.5 Pro** | ~2 | ~50,000 | ~25 | 已极度受限 |
| **Imagen 4 / Nano Banana** | 2 IPM | – | 极低 | 图像生成单独限额 |

> **重要规则**：
> - 限额按 **Google Cloud 项目（project）** 计算，而非按 API Key。同一项目下创建多个 Key 不会增加配额。
> - 免费层**没有 Token 总量上限**，只有速率/日请求上限。RPD 达到上限后当日无法继续调用。

### 2.4 过期机制

- **免费额度**: 无过期一说，因为不是预充值模式。限制是速率/日请求上限。
- **重置规则**：
  - **RPD（日请求限额）**：在 **太平洋时间午夜（PT midnight，即 UTC 08:00）** 重置。
  - **RPM/TPM**：滚动 60 秒窗口，持续释放容量。
- **Rollover**: 无。当日未用完的 RPD 不累积至次日。
- **退款**: 不适用（免费层无费用）。

### 2.5 API 可用性

- **非常易于获取**。访问 aistudio.google.com → 用 Google 账号登录 → 点击 "Get API Key" 即可立即生成 `AIza...` 格式的 API Key。
- 无需 Cloud Billing 账号、无需 GCP 项目手动配置。是门槛最低的官方 API 获取路径之一。

### 2.6 数据隐私与训练使用

**关键条款**：免费层 Google AI Studio 的输入/输出数据**可能被 Google 用于改进其模型**，且可能被人工评估员审查。官方建议**不要在免费层提交敏感、机密或个人数据**。
- 付费层（绑定 Cloud Billing 后）承诺不将客户提示和响应用于模型训练。
- 欧洲经济区（EEA）、瑞士、英国用户即使在免费层也享有不用于训练的保护。

### 2.7 模型能力关键参数

- 免费层可访问的模型与付费层一致，仅受速率限制约束。
- 支持多模态输入（文本、图片、音频、视频、文档）。
- 支持 1M tokens 上下文（Flash 系列）。
- 支持 Function Calling / 工具调用。
- 支持上下文缓存（Context Caching，但缓存内容需付费时才完整启用）。

### 2.8 支付方式与地区

- **免费层**：无需任何支付方式。
- **升级至付费**：需绑定 Cloud Billing 账号，接受**实体国际信用卡**（Visa、Mastercard）。
- **不接受的卡**：预付卡（Prepaid Cards）、虚拟信用卡（VCC）通常会被 Google Cloud Billing 的风控系统拦截。
- 据实测反馈，招商银行全币种 Visa 等实体外币卡可正常使用；纯虚拟 U 卡容易被拒绝。

---

## 3. Gemini API（按量付费）

### 3.1 平台名称与定价

Gemini API 通过 Google AI Studio 付费层或 Vertex AI 提供，按每百万 tokens 计费。价格分为 **≤200K tokens** 和 **>200K tokens** 两个档位（长上下文 surcharge）。

#### 3.1.1 标准模型定价（per 1M tokens）

| 模型 | 输入（≤200K） | 输入（>200K） | 缓存输入 | 输出（≤200K） | 输出（>200K） | 上下文 |
|-----|--------------|--------------|---------|--------------|--------------|-------|
| **Gemini 3.5 Flash** | $1.50 | – | $0.15 | $9.00 | – | 1M |
| **Gemini 3.1 Pro Preview** | $2.00 | $4.00 | $0.20 / $0.40 | $12.00 | $18.00 | 1M–2M |
| **Gemini 3 Flash Preview** | $0.50 | $1.00 (audio) | $0.05 / $0.10 | $3.00 | – | 1M |
| **Gemini 3.1 Flash-Lite Preview** | $0.25 | $0.50 (audio) | $0.025 / $0.05 | $1.50 | – | 1M |
| **Gemini 2.5 Pro** | $1.25 | $2.50 | $0.125 / $0.25 | $10.00 | $15.00 | 1M |
| **Gemini 2.5 Flash** | $0.30 | $1.00 (audio) | $0.03 / $0.10 | $2.50 | – | 1M |
| **Gemini 2.5 Flash-Lite** | $0.10 | $0.30 (audio) | $0.01 / $0.03 | $0.40 | – | 1M |
| **Gemini Embedding 2** | $0.20 (text) / $0.45 (image) / $6.50 (audio) / $12.00 (video) | – | – | – | – | – |

#### 3.1.2 计费模式

- **Standard 标准**: 上述常规价格。
- **Batch 批量**: 所有模型 **50% 折扣**，SLA 为最长 24 小时返回。
- **Cached Input 缓存输入**: 对重复使用的上下文（如固定系统提示），缓存后仅需支付约 **10% 的常规输入价格**。
- **按实际用量计费**：后付费，无预付要求。

### 3.2 Token 额度与调用限制

- 付费层无固定 Token 配额上限，取决于账户的 **Usage Tier**：
  - **Tier 1**: 绑定 Billing Account 即可，无最低消费。
  - **Tier 2**: 累计消费 $50 + 首次付费后 7 天。
  - **Tier 3**: 累计消费 $250 + 首次付费后 30 天。
  - 更高 Tier 可通过 Google Cloud 客户经理协商。
- 限额维度：RPM、TPM、RPD 随 Tier 提升而扩大。

### 3.3 过期机制

- **按量计费模式**：无预付额度，无过期问题。每月按实际使用量生成账单。
- **Google Cloud $300 新用户赠金**：
  - 有效期 **90 天**。
  - **关键限制**：据 2026 年 3 月后官方明确说明，此赠金**不能用于支付 Gemini API 或 AI Studio 的用量费用**，仅可用于其他 Google Cloud 产品。
- **退款**：按量计费模式下，已使用的 API 调用费用通常不可退款。异常扣费可联系 Google Cloud Support 申诉。

### 3.4 API 可用性

- **非常易于获取**：通过 Google AI Studio 获取 API Key 后，在请求中加入 `?key=AIza...` 即可调用。
- 也支持通过 Vertex AI SDK 或 REST API 直接调用。
- 个人开发者和小团队均可快速开通。

### 3.5 模型能力关键参数

与上述模型参数相同，付费层解锁全部能力，包括：
- 完整上下文窗口（最高 2M tokens on 1.5 Pro / Vertex Enterprise）。
- 完整多模态支持（文本、图像、音频、视频、文档、PDF 解析）。
- **Function Calling / Tool Use**：支持声明工具，模型可自动调用外部 API。
- **MCP (Model Context Protocol)** 兼容。
- **Context Caching**：缓存长上下文以降低重复输入成本。
- **Batch API**：异步批量处理，半价。
- **Grounding**：支持 Google Search  grounding（搜索结果增强生成）。

---

## 4. Vertex AI（企业级托管）

### 4.1 平台名称与套餐

- **平台名称**: Google Cloud Vertex AI
- **定位**: 企业级 MLOps 平台，托管 Gemini 模型并提供额外企业功能。

### 4.2 定价

Vertex AI 的 Gemini 模型定价与 Gemini API 基本一致，但增加了额外层级：

| 服务层级 | Gemini 3.1 Pro 输入 | 输出 | 特点 |
|---------|-------------------|------|------|
| **Standard** | $2.00 / $4.00 (>200K) | $12.00 / $18.00 (>200K) | 大多数生产负载 |
| **Priority** | $3.60 / $7.20 (>200K) | $21.60 / $32.40 (>200K) | 延迟敏感，保证吞吐量（约贵 80%） |
| **Flex / Batch** | $1.00 / $2.00 (>200K) | $6.00 / $9.00 (>200K) | 非紧急批量任务，50% 折扣 |

- 另有模型托管基础设施费用（端点部署费）、网络出站流量费等。
- 企业客户可协商自定义价格。

### 4.3 Token 额度与调用限制

- 无固定 Token 总量上限，受项目配额和 Usage Tier 限制。
- 通过 GCP Quotas 页面可申请提升限额。
- 企业客户可获得 SLA 保障的吞吐量。

### 4.4 过期机制

- **按量计费**：无预付额度过期问题。
- **$300 新用户赠金**：90 天有效，**不适用于 Gemini API 费用**（2026 年 3 月 2 日后新账号适用此规则）。
- **承诺使用折扣（Committed Use Discounts）**：可购买 1 年或 3 年承诺，换取折扣。未用完的承诺额度不退款。

### 4.5 API 可用性

- **需 Google Cloud 项目 + Billing Account**：门槛高于 AI Studio。
- 通过 Vertex AI SDK 或 GCP Console 获取端点信息。
- 支持 VPC Service Controls、客户管理的加密密钥、区域驻留等 enterprise 功能。
- **数据驻留（Data Residency）**：支持在指定区域处理数据。
- **零数据保留（Zero Data Retention）**：符合条件的企业客户可通过合同修订实现。

### 4.6 模型能力关键参数

- 提供与 Gemini API 相同的模型系列。
- 额外支持：
  - **微调（Fine-tuning）**：可在自有数据上微调 Gemini 模型。
  - ** grounding with Google Search**：搜索结果增强。
  - **多区域推理**：跨区域负载均衡。
  - **自定义端点**：私有化模型部署。

### 4.7 支付方式与地区

- **必须绑定 Google Cloud Billing Account**。
- **接受的支付方式**：实体信用卡、借记卡、银行账户（ACH/SEPA 等，取决于国家）。
- **不接受的支付方式**：预付卡、虚拟信用卡（VCC）通常被风控系统拒绝。
- **地区**：Vertex AI 支持 Google Cloud 运营的大多数国家/地区。中国大陆不在直接服务范围内（需通过香港、台湾、新加坡等区域）。
- **币种**：按 Google Cloud Billing 账号设置币种结算，支持美元、欧元、日元、英镑等。

---

## 5. 模型能力关键参数（总览）

| 模型 | 上下文窗口 | 输出上限 | 多模态 | 推理 | 代码 | 工具调用 | 成本定位 |
|-----|-----------|---------|--------|------|------|---------|---------|
| **Gemini 3.1 Pro** | 1M–2M | 64K | 文本/图/音/视频 | ⭐⭐⭐ 旗舰 | ⭐⭐⭐ | ✅ | 高 |
| **Gemini 3.5 Flash** | 1M | 64K | 文本/图/音/视频 | ⭐⭐⭐ | ⭐⭐⭐ | ✅ | 中高（性价比旗舰）|
| **Gemini 3 Flash** | 1M | 32K | 文本/图/音/视频 | ⭐⭐ | ⭐⭐ | ✅ | 中 |
| **Gemini 3.1 Flash-Lite** | 1M | 32K | 文本/图/音/视频 | ⭐⭐ | ⭐⭐ | ✅ | 低 |
| **Gemini 2.5 Pro** | 1M | 64K | 文本/图/音/视频 | ⭐⭐⭐ Thinking | ⭐⭐⭐ | ✅ | 中高 |
| **Gemini 2.5 Flash** | 1M | 32K | 文本/图/音/视频 | ⭐⭐ | ⭐⭐ | ✅ | 低 |
| **Gemini 2.5 Flash-Lite** | 1M | 32K | 文本/图/音/视频 | ⭐⭐ | ⭐⭐ | ✅ | **最低** |
| **Gemini 1.5 Pro** | 2M（可升级） | 32K | 文本/图/音/视频 | ⭐⭐ | ⭐⭐ | ✅ | 中（旧旗舰）|

### 5.1 关键能力详解

- **多模态**: 原生支持，可同时处理文本、高分辨率图像、音频（含环境音、音乐）、视频（最长 3 小时/1M tokens）。
- **代码执行**: 模型可在沙箱中直接执行 Python 代码（NumPy, Pandas, Matplotlib 等），支持数据分析和可视化。
- **实时音频**: Live API 支持双向语音流，可调节音色和风格。
- **Project Mariner**: 仅限 Ultra 订阅，支持 Agentic 浏览器控制（点击、输入、读取屏幕）。
- **图像生成**: Nano Banana（Gemini 2.5 Flash Image）和 Nano Banana Pro（Gemini 3 Pro Image）支持内联图像生成。
- **MCP 支持**: 2.5 Pro 和 3.x 系列支持 Model Context Protocol，可声明工具、知识库和上下文。

---

## 6. ToS 与政策条款

### 6.1 适用条款文档

| 服务路径 | 适用条款 |
|---------|---------|
| Gemini App（消费者） | Google Terms of Service + Google One Additional Terms |
| Google AI Studio 免费层 | Gemini API Terms of Service – Unpaid Services |
| Google AI Studio / Gemini API 付费 | Gemini API Terms of Service – Paid Services |
| Vertex AI | Google Cloud Platform Terms of Service + Data Processing Addendum |
| Gemini Code Assist | Gemini Code Assist for Individuals ToS / Enterprise ToS |

### 6.2 关于账号共享与转售的条款

由于无法直接访问 Google 动态 ToS 页面的完整原文，以下为基于公开文档和开发者论坛经验的综合整理：

#### 6.2.1 已明确的限制

1. **禁止通过第三方工具未授权访问服务**：
   > "Directly accessing the services powering Gemini CLI (for example, the Gemini Code Assist service) using third-party software, tools, or services... is a violation of applicable terms and policies. Such actions may be grounds for suspension or termination of your account."
   > — 来源：Gemini CLI 官方文档

2. **多账户滥用检测**：Google 在 2026 年初进行了大规模 "系统级解封"，此前大量账号因被判定为滥用（如通过 OpenClaw 等工具循环调用 OAuth）而被暂停。独立 API Key（`AIza...`）比 OAuth 会话更不容易触发风控。

3. **Google Cloud Platform Terms of Service 通常包含**：
   - 禁止对服务进行 resale、sublicense 或商业性再分发。
   - 禁止将服务用于与第三方共享的纯转售场景（除非有明确合作伙伴协议）。
   - 禁止绕开技术限制或创建多账户以规避配额。

4. **共享网络环境风险**：Google AI Developers Forum 有案例显示，约 20 人团队在同一办公室网络使用各自账号和 API Key 进行开发，因共享出口 IP 和集中支付方式被系统同时标记为 "regional restriction"，需要人工申诉。

#### 6.2.2 未找到公开信息的领域

- **Gemini Advanced 消费者订阅是否明确禁止家庭/团队共享账号**：未找到直接条款。但 Google 通用服务条款通常禁止将账号凭证提供给第三方使用。
- **Gemini API Key 是否允许在组织内部共享**：根据 GCP 惯例，API Key 可在同一项目内由团队使用，但共享给项目外部第三方可能触发滥用检测。
- **API Key 的 sublicensing 明文禁止条款**：未找到逐字引用，但 Google Cloud ToS 中的知识产权和使用权限制通常涵盖此范围。

### 6.3 数据使用与隐私政策

| 层级 | 是否用于训练 | 数据保留 | 人工审查 |
|-----|------------|---------|---------|
| **Google AI Studio 免费层** | ✅ 可能使用 | 标准保留 | 可能 |
| **Gemini API 付费层** | ❌ 不用于训练 | 有限保留（安全/合规） | 仅安全审核 |
| **Vertex AI** | ❌ 不用于训练 | 可配置，支持 ZDR | 企业级控制 |
| **EEA/瑞士/英国** | ❌ 所有层级不训练 | 标准 | 受限 |

---

## 7. 支付方式与地区限制

### 7.1 各平台支付方式

| 平台/套餐 | 信用卡 | 借记卡 | 预付卡 | 虚拟卡 | PayPal | App Store | Google Play | 备注 |
|----------|--------|--------|--------|--------|--------|-----------|-------------|------|
| **Gemini Advanced（消费订阅）** | ✅ | ✅ | ⚠️ | ⚠️ | 部分地区 | ✅ | ✅ | 取决于购买渠道 |
| **Google AI Studio 免费层** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 无需支付 |
| **Google AI Studio 付费升级** | ✅ 实体 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | 需 Cloud Billing |
| **Vertex AI / GCP Billing** | ✅ 实体 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | 严格风控 |

### 7.2 地区限制与可用性

- **全球服务**：Google AI Studio 和 Gemini API 在大多数国家和地区可用。
- **受限地区**：受制裁国家（如朝鲜、伊朗、叙利亚、克里米亚等）被明确禁止。中国大陆不在 Google Cloud 部分服务直接覆盖范围内，需通过香港/台湾/新加坡区域使用。
- **Google Cloud Billing 国家/地区**：支持 200+ 国家/地区，但支付方式因国家而异。部分国家仅支持特定信用卡或银行转账。
- **语言支持**：Gemini 模型支持 100+ 语言，包括中文（简体/繁体）。

### 7.3 计费币种与税务

- Google Cloud 默认按美元计费（可设置本地币种）。
- 消费者订阅（Google AI Pro/Ultra）通常按当地货币显示，但底层以美元计价。
- 可能收取当地增值税（VAT）或消费税，取决于用户所在司法管辖区。

---

## 8. 总结对比表

| 维度 | Gemini Advanced（消费） | Google AI Studio（免费） | Gemini API（按量） | Vertex AI（企业） |
|-----|------------------------|------------------------|-------------------|------------------|
| **目标用户** | 个人消费者 | 开发者/原型验证 | 开发者/生产应用 | 企业/团队 |
| **月费** | $7.99–$200 | $0 | 按量（$0.10–$4.00/1M 输入） | 按量 + 基础设施费 |
| **API Key** | ❌ | ✅ 免费获取 | ✅ 免费获取 | ✅ 需 GCP 项目 |
| **上下文上限** | 1M tokens | 1M tokens | 1M–2M tokens | 1M–2M tokens |
| **免费额度** | 无（订阅制） | 速率限制 | 无（纯按量） | $300 赠金（90天，不含API） |
| **额度过期** | 月重置 | 日重置 | 无预付 | 赠金90天 |
| **Rollover** | 未找到 | 无 | 不适用 | 不适用 |
| **数据用于训练** | 未明确 | ✅ 可能 | ❌ | ❌ |
| **SLA** | 无 | 无 | 无 | ✅ 有 |
| **多模态** | ✅ | ✅ | ✅ | ✅ |
| **工具调用** | 有限 | ✅ | ✅ | ✅ |
| **VPC/私有部署** | ❌ | ❌ | ❌ | ✅ |
| **合规认证** | 无 | 无 | 无 | SOC2, HIPAA 可选 |

---

## 参考资料

1. Gemini Pricing 2026: Plans, API & Workspace Cost Guide — felloai.com (2026-06-29)
2. Google Gemini Context Window: Token Limits, Model Comparison — datastudios.org (2025-12-15)
3. Gemini API Free Tier Limits 2026: the Billing Trap That Deletes Them — usagebox.com (2026-06)
4. Gemini Image Generation Free Limits 2026 — blog.laozhang.ai (2026-02-24)
5. Google AI Studio Free Plans, Trials, and Subscriptions — datastudios.org (2025-10-11)
6. Gemini CLI: License, Terms of Service, and Privacy Notices — geminicli.com (2026-04-10)
7. Google Gemini Data Retention Policy 2026 — meetily.ai (2026-06-29)
8. Vertex AI vs Google AI Studio — useaiapi.com (2026-06-09)
9. Why Do Virtual Cards Fail When Subscribing to AI Services? — biyapay.com (2026-06-22)
10. Gemini 2.5: Pushing the Frontier with Advanced Reasoning — arxiv.org (2025-07-07)
11. Gemini API Pricing May 2026 — metacto.com (2026-06-11)
12. Gemini 2.5 Flash Preview Pricing — pricepertoken.com (2026-07-08)
13. Google AI Studio Pricing: Free Tier, API Costs & Limits — deploybase.ai (2026-02-05)
14. Google AI Studio Free Tier 2026 — pricepertoken.com (2026-04)

> **免责声明**: 本报告基于公开网络信息整理，定价和条款可能随时变化。请以 Google 官方最新页面（ai.google.dev, cloud.google.com）为准。部分 ToS 细节因无法直接访问实时页面，标注为"未找到公开信息"。
