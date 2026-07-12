# AI API平台调研报告：Mistral API / Le Chat、Cohere API、Fireworks API、Together AI API

> **调研日期**：2026年7月10日
> **调研目的**：分析各平台定价、额度机制、API可用性、ToS条款，评估是否适合二手Token转售
> **调研方法**：网络搜索（kimi_search_v2）、官网抓取（kimi_fetch_v2）、第三方定价数据库

---

## 一、Mistral AI（API + Le Chat）

### 1. 平台概述
Mistral AI 是法国AI公司，提供消费级产品 Le Chat 和开发者API（La Plateforme）。以欧洲隐私优先、GDPR合规为卖点。

### 2. 定价信息

#### Le Chat（消费端聊天产品）

| 套餐 | 月费 | 额度/限制 | 关键特性 |
|------|------|-----------|----------|
| **Free** | $0 | ~25条消息/天软限制 | 核心模型、图像生成、代码解释器、40+连接器、500 memories |
| **Pro** | $14.99/月（学生$5.99/月） | ~150条消息/天（约6x Free） | 所有模型、No Telemetry模式、15GB存储、Mistral Vibe、优先响应 |
| **Team** | $24.99/用户/月（年付$19.99） | 共享更高限制 | 30GB/用户、共享RAG库、管理员控制、数据导出 |
| **Enterprise** | 定制报价 | 定制 | 私有部署、SSO、审计日志、定制模型、EU数据驻留 |

> **注意**：Le Chat 订阅与 API 计费完全分离。Le Chat Pro 不包含任何 API 额度。

#### API（开发者平台 La Plateforme）

| 模型 | 输入 ($/1M tokens) | 输出 ($/1M tokens) | 上下文长度 | 适用场景 |
|------|-------------------|-------------------|-----------|----------|
| **Mistral Small 3.1 24B** | $0.10 | $0.30 | 128K | 高容量、成本敏感任务 |
| **Mistral Small 3.2 24B** | $0.075 | $0.200 | 131K | 更快、更便宜的全能模型 |
| **Mistral Medium 3** | $0.40 | $2.00 | 131K | 平衡性能与成本 |
| **Mistral Medium 3.5** | $1.50 | $7.50 | 128K | 更强推理能力 |
| **Mistral Large 3** | $0.50 | $1.50 | 262K | 旗舰模型（2025年12月发布） |
| **Codestral** | $0.30 | $0.90 | 256K | 代码专用模型 |
| **Devstral Small 2505** | **免费** | **免费** | - | 代码模型（限时免费） |
| **Ministral 3B** | $0.04 | $0.04 | - | 最小边缘模型 |
| **Mistral Embed** | $0.10 | $0.10 | - | 嵌入模型 |
| **Pixtral Large** | $2.00 | $6.00 | - | 视觉模型 |

> **定价模式**：纯按量付费（Pay-as-you-go），无月费最低消费。新API账户 reportedly 可获得 $25-$50 试用额度。

### 3. Token额度与调用限制

| 层级 | 额度/限制 | 说明 |
|------|-----------|------|
| **Free Experiment Plan** | ~10亿 tokens/月 | 仅用于评估，rate-limited，不需信用卡，需手机验证 |
| **付费生产级** | 按量计费，无上限 | 标准 rate limits 由控制台管理 |
| **企业级** | 定制 | 可协商更高限额和SLA |

### 4. 过期机制
- **API额度**：按量付费无过期概念，用多少付多少
- **试用额度**：未找到明确的过期时间公开信息
- **Le Chat订阅**：按月订阅，月度重置消息限制，无rollover
- **余额退款**：未找到明确的退款政策公开信息

### 5. API可用性
- **API Key获取**：容易。注册账户后自动创建 Trial API key，升级为生产级需完成 Billing 设置
- **个人用户友好度**：高。无需信用卡即可试用（Free Experiment Plan），仅需手机验证
- **OpenAI兼容**：是，支持 OpenAI-compatible endpoints

### 6. ToS相关条款（转售/共享限制）

根据 Mistral AI 使用条款（从第三方文档引用）：

> **明确禁止行为**：
> - "Not grant a license, sub-licence, or access to or sell, lend, lease or distribute, in any form whatsoever, the Services to third parties without the prior written authorization of Mistral AI."
> - "Not make the Services accessible to third parties, unless otherwise stated."
> - "Not incorporate Our Services into Your products and/or services, unless otherwise stated."
> - "Not use Outputs to reverse-engineer Our Services."

**转售适用性评估**：❌ **不适合**。Mistral明确禁止未经许可向第三方出售、分发、授权或提供访问服务，禁止将服务整合到第三方产品中。

### 7. 模型能力关键参数

| 能力 | 详情 |
|------|------|
| **上下文长度** | 128K - 262K tokens（视模型而定） |
| **多模态** | 支持（Pixtral视觉模型、部分模型支持图像输入） |
| **推理能力** | Command A Reasoning（推理模型）、Magistral Medium |
| **代码能力** | Codestral（256K上下文，代码专用）、Devstral |
| **工具调用** | 支持（Tool use/Function calling） |
| **RAG/检索** | 原生支持，内置文档连接器 |
| **嵌入** | Mistral Embed 支持 |
| **语音** | Voxtral（语音模型） |
| **零数据保留** | Pro及以上可开启 No Telemetry Mode |

### 8. 支付方式
- **信用卡**：支持全球主流信用卡
- **账单周期**：按月出账，或达到$250未结余额时触发账单
- **地区限制**：欧盟数据驻留可选，全球可用
- **其他**：企业客户支持定制合同和发票

---

## 二、Cohere API

### 1. 平台概述
Cohere 是加拿大AI公司，专注于企业级RAG（检索增强生成）和Embed/Rerank技术栈。提供Command系列生成模型、Embed嵌入模型、Rerank重排序模型。

### 2. 定价信息

#### API按量付费定价

| 模型 | 输入 ($/1M tokens) | 输出 ($/1M tokens) | 上下文长度 | 说明 |
|------|-------------------|-------------------|-----------|------|
| **Command R7B** | $0.0375 | $0.15 | 128K | 最便宜的生产模型 |
| **Command R (08-2024)** | $0.15 | $0.60 | 128K | 平衡型RAG优化 |
| **Command R+ (08-2024)** | $2.50 | $10.00 | 128K | 旗舰级 |
| **Command A** | $2.50 | $10.00 | 256K | 最新旗舰（MoE架构） |
| **Command A+** | 联系销售 | 联系销售 | 128K | 最新旗舰（MoE+多模态） |
| **Command A Reasoning** | 联系销售 | 联系销售 | 256K | 推理模型 |
| **Command A Vision** | 联系销售 | 联系销售 | 128K | 视觉模型 |
| **Aya Expanse 32B** | $0.50 | $1.50 | 128K | 多语言模型（23种语言） |
| **Embed v4 (Text)** | $0.12 | - | 128K | 文本嵌入 |
| **Embed v4 (Image)** | $0.47 | - | 128K | 图像嵌入 |
| **Embed v3** | $0.10 | - | 512 | 旧版嵌入 |
| **Rerank v3** | $2.00/1K searches | - | 4K | 重排序（按搜索计费） |
| **Rerank v4 Pro** | $2.00/1K searches | - | 32K | 新版重排序 |
| **Legacy Command** | $1.00 | $2.00 | 4K | 旧版（现有客户） |
| **Legacy Command-light** | $0.30 | $0.60 | 4K | 旧版轻量 |

> **定价模式**：纯按量付费，无月费。账单在每月月底或达到$250未结余额时生成。

#### 企业产品（North / Compass / Model Vault）

| 产品 | 定价模式 | 说明 |
|------|----------|------|
| **North** | 定制报价 | 企业AI平台，All-in-one |
| **Compass** | 定制报价 | 智能搜索和发现系统 |
| **Model Vault** | 按实例小时/月 | Embed 4 Small: $4/hr或$2,500/月；Embed 4 Medium: $5/hr或$3,250/月；Rerank系列: $5-$10/hr |

### 3. Token额度与调用限制

| API Key 类型 | 月度额度 | 速率限制 | 说明 |
|-------------|----------|----------|------|
| **Trial Key** | 1,000 API calls/月 | Chat: 20 req/min; Rerank: 10 req/min; Embed: 2,000 inputs/min（文本）| 免费，仅用于评估/原型，**禁止生产/商业用途** |
| **Production Key** | 无限制（按量付费） | Chat: 500 req/min; 其他: 1,000 req/min | 需完成 Billing 申请，Owner权限 |
| **Enterprise** | 定制 | 定制 | 联系销售 |

> **注意**：Trial Key 的 1,000 calls/月 是所有端点共享的硬上限。

### 4. 过期机制
- **Trial额度**：1,000 calls/月，月度重置，不可rollover
- **Production按量付费**：无过期，用多少付多少
- **账单触发**：每月月底或$250未结余额时出账
- **退款政策**：未找到明确的预付费余额退款政策

### 5. API可用性
- **API Key获取**：注册后自动获得Trial Key。Production Key需组织Owner权限并填写申请流程
- **个人用户友好度**：中等。Trial Key免费且无需信用卡，但Production Key需要组织结构和账单设置
- **企业审批**：Production Key需要组织账户和审批流程

### 6. ToS相关条款（转售/共享限制）

根据 Cohere 官方文档和第三方引用：

> **明确禁止行为**：
> - Trial keys "are not permitted to be used for production or commercial purposes"
> - "rent, lease, sell, resell, assign, sublicense, transfer, distribute any or all of the Service"
> - "use the Service in any manner intended to avoid incurring fees (including creating multiple accounts to simulate or act as a single customer account)"
> - "make the Services accessible to third parties"
> - "incorporate Our Services into Your products and/or services, unless otherwise stated"

**转售适用性评估**：❌ **不适合**。Cohere明确禁止resell、sublicense、transfer服务，禁止将服务整合到第三方产品中，且Trial Key禁止商业用途。

### 7. 模型能力关键参数

| 能力 | 详情 |
|------|------|
| **上下文长度** | 128K（Command系列），256K（Command A） |
| **多模态** | Command A Vision支持图像输入；Embed v4支持图像嵌入 |
| **推理能力** | Command A Reasoning支持推理链 |
| **代码能力** | North Mini Code（代码专用模型） |
| **工具调用** | 支持（Tool use/Agents） |
| **RAG/检索** | **核心优势**，原生支持RAG、Grounding、Inline Citations |
| **嵌入** | Embed v4/v3，多语言，多模态 |
| **重排序** | Rerank v4/v3，独特竞争力 |
| **语音** | Cohere Transcribe（ASR，开源研究版） |
| **多语言** | Aya系列支持23-70种语言 |

### 8. 支付方式
- **信用卡**：支持全球主流信用卡
- **账单周期**：每月月底或$250未结余额时触发
- **企业支付**：支持ACH、Wire Transfer等（需清算时间）
- **地区限制**：全球可用，企业部署支持AWS、Azure、Oracle OCI
- **其他**：企业客户支持定制合同

---

## 三、Fireworks AI API

### 1. 平台概述
Fireworks AI 是专注于快速推理（fast inference）的AI平台，主打开源模型托管和优化推理。以Fire-function calling和零数据保留为卖点。

### 2. 定价信息

#### Serverless 按量付费（部分模型示例，2026年6月）

| 模型 | 输入 ($/1M tokens) | 输出 ($/1M tokens) | 上下文 | 说明 |
|------|-------------------|-------------------|--------|------|
| **Llama 3.3 70B** | $0.88 | $0.88 | 128K | 热门开源模型 |
| **Llama 3 8B Instruct Lite** | $0.10 | $0.10 | 8K | 轻量版 |
| **Mixtral 8x22B** | $0.24 | $0.72 | 64K | MoE架构 |
| **DeepSeek-V4-Pro** | $1.74 | $3.48 | 512K | 长上下文 |
| **Kimi K2.6** | $0.95 | $4.00 | 262K | Moonshot模型 |
| **Qwen3.5 9B** | $0.10 | $0.15 | 262K | 小型多语言 |
| **Qwen3.5 397B A17B** | $0.60 | $3.60 | 262K | 大型MoE |
| **GPT-OSS 20B** | $0.05 | $0.20 | 128K | OpenAI开源 |
| **GPT-OSS 120B** | $0.15 | $0.60 | 128K | OpenAI开源 |
| **Gemma 4 31B** | $0.20 | $0.50 | 262K | Google开源 |
| **Gemma 3N E4B** | $0.06 | $0.12 | 32K | 超小型 |
| **LFM2-24B-A2B** | $0.03 | $0.12 | 32K | 最便宜的模型之一 |
| **Llama 2 7B**（历史） | $0.075 | $0.225 | - | 旧版参考 |
| **Code Llama 34B**（历史） | $0.45 | $1.35 | - | 代码模型 |

> **折扣机制**：
> - **Cached input**：所有文本和视觉模型默认50%折扣
> - **Batch inference**：Serverless价格的50%折扣
> - **Volume折扣**：$100-1,000/月（5-10%），$1,000-10,000/月（10-20%），$10,000+/月（定制）
> - **Burst pricing**：1,000-5,000 req/s（10%附加费），5,000+ req/s（25%附加费）

#### 图像模型定价（按百万像素/张）

| 模型 | 价格 | 说明 |
|------|------|------|
| **FLUX.1 [schnell]** | $0.0027/MP | 4步默认 |
| **FLUX.2 [dev]** | $0.0154/MP | - |
| **FLUX.2 [pro]** | $0.03/MP | - |
| **Stable Diffusion 3** | $0.0019/MP | - |
| **SD XL** | $0.0019/MP | - |
| **Imagen 4.0 Fast** | $0.02/MP | Google |
| **Imagen 4.0 Ultra** | $0.06/MP | Google |
| **Seedream 3.0** | $0.018/MP | 字节跳动 |
| **Qwen Image** | $0.0058/MP | 阿里 |

#### 视频模型定价（按视频/段）

| 模型 | 价格 | 分辨率/时长 |
|------|------|-------------|
| **Veo 3.0 Fast** | $0.80 | 1080p / 8s |
| **Veo 3.0** | $1.60 | 720p / 8s |
| **Kling 2.1 Standard** | $0.18 | 720p / 5s |
| **Kling 2.1 Pro** | $0.32 | 1080p / 5s |
| **Seedance 1.0 Lite** | $0.14 | 720p / 5s |

#### 其他定价

| 服务 | 定价 |
|------|------|
| **Embeddings** | $0.008-$0.016/1M tokens（视模型参数量） |
| **Fine-tuning (LoRA SFT, ≤16B)** | $0.50/1M training tokens |
| **Fine-tuning (Full SFT, >300B)** | $20.00/1M training tokens |
| **On-demand GPU (H100)** | $7.00/小时 |
| **On-demand GPU (H200)** | $7.00/小时 |
| **On-demand GPU (B200)** | $10.00/小时 |
| **On-demand GPU (B300)** | $12.00/小时 |

### 3. Token额度与调用限制

| 层级 | 额度 | 速率限制 | 说明 |
|------|------|----------|------|
| **新用户（无支付方式）** | $1 免费credit | 10 RPM | 纯试用，无需信用卡 |
| **添加支付方式后** | 按量付费 | 最高 6,000 RPM | 月消费层级：$50 → $500 → $5,000 → $50,000 |
| **企业级** | 定制 | 定制 | 联系销售 |

> **注意**：Fireworks的6,000 RPM是固定硬上限，即使最高消费层级也不能突破。

### 4. 过期机制
- **$1免费credit**：未找到明确的过期时间，但属于starter credit，通常用于评估
- **按量付费余额**：预付费模式，用多少扣多少，余额不足时需充值
- **退款政策**：根据ToS，"Fees paid are non-refundable"（已支付费用不可退款），除非适用法律要求
- **订阅取消**：需提前3天通知，取消后当前周期内仍可使用

### 5. API可用性
- **API Key获取**：容易。注册账户即可获得，支持OpenAI-compatible API格式
- **个人用户友好度**：高。$1免费credit无需信用卡，支持cURL和Python SDK快速测试
- **中国大陆访问**：需要代理/relay（文档明确说明"Requires proxy in China"）

### 6. ToS相关条款（转售/共享限制）

根据 Fireworks AI Terms of Service（2026年7月1日更新）：

> **明确禁止行为（Section 2.2）**：
> - "(d) buy, sell or transfer API keys without our prior written consent in each case"
> - "(e) copy, rent, lease, sell, loan, transfer, assign, license or purport to sublicense, resell, distribute, modify, alter, or create derivative works of any part of the Service"
> - "(i) use or display the Service in competition with us, to develop competing products or services"
> - "(n) use the Service for commercial solicitation"
> - "(v) charges you incur will be honored by your Payment Method company; (vi) you will not allow or enable anyone else to use your Subscription"

> **账户安全（Section 1.2d）**：
> - "You will not share your password(s) and/or any other authentication credentials with anyone else"

**转售适用性评估**：❌ **不适合**。Fireworks明确禁止未经书面同意买卖或转让API Key，禁止resell、sublicense、transfer服务，禁止共享认证凭证。

### 7. 模型能力关键参数

| 能力 | 详情 |
|------|------|
| **上下文长度** | 8K - 512K tokens（视模型而定，DeepSeek-V4-Pro支持512K） |
| **多模态** | 支持图像模型（FLUX、Stable Diffusion、Imagen等）、视频模型、视觉模型（Gemma Vision等） |
| **推理能力** | 支持DeepSeek R1等推理模型 |
| **代码能力** | 支持Code Llama、DeepSeek Coder等 |
| **工具调用** | 支持Function calling（Fire-function calling为 proprietary 优势） |
| **结构化输出** | Fire-function calling优化，比标准生成快75%、省80%token |
| **嵌入** | 支持Multilingual-e5等 |
| **零数据保留** | 默认零数据保留（"Zero Data Retention"政策），不存储prompt或生成数据 |
| **合规** | SOC 2 Type II、HIPAA合规 |

### 8. 支付方式
- **信用卡**：Stripe处理，支持全球主流信用卡
- **ACH/Wire**：支持，但需清算时间（credit到账前不可用）
- **账单周期**：预付费+自动充值模式（余额低于阈值时自动扣款）
- **地区限制**：全球可用，但中国大陆需代理
- **其他**：企业客户可协商定制合同；非营利和学术机构 reportedly 可获50%折扣

---

## 四、Together AI API

### 1. 平台概述
Together AI 是开源模型推理平台，提供Serverless端点、Dedicated GPU租赁、Fine-tuning和Batch推理服务。以高性能推理和开源模型生态为卖点。

### 2. 定价信息

#### Serverless 按量付费（部分热门模型，2026年6月）

| 模型 | 输入 ($/1M tokens) | 缓存输入 ($/1M) | 输出 ($/1M tokens) | 上下文 | 量化 |
|------|-------------------|-----------------|-------------------|--------|------|
| **MiniMax M2.7** | $0.30 | $0.06 | $1.20 | 202K | FP4 |
| **Qwen3.5 397B A17B** | $0.60 | - | $3.60 | 262K | FP4 |
| **Qwen3.6 Plus** | $0.50 | - | $3.00 | 1,000K | - |
| **Kimi K2.6** | $1.20 | $0.20 | $4.50 | 262K | FP4 |
| **Kimi K2.5** | $0.50 | - | $2.80 | 262K | FP4 |
| **GLM-5.1** | $1.40 | - | $4.40 | 202K | FP4 |
| **GLM-5** | $1.00 | - | $3.20 | 202K | FP4 |
| **GPT-OSS 120B** | $0.15 | - | $0.60 | 128K | MXFP4 |
| **GPT-OSS 20B** | $0.05 | - | $0.20 | 128K | MXFP4 |
| **DeepSeek-V4-Pro** | $2.10 | $0.20 | $4.40 | 512K | FP4 |
| **DeepSeek R1** | $3.00 | - | $7.00 | 163K | - |
| **Llama 3.3 70B Instruct Turbo** | $0.88 | - | $0.88 | 131K | FP8 |
| **Qwen3-Coder 480B** | $2.00 | - | $2.00 | 256K | FP8 |
| **Qwen3 235B-A22B** | $0.20 | - | $0.60 | 262K | FP8 |
| **Gemma 4 31B** | $0.20 | - | $0.50 | 262K | FP8 |
| **Gemma 3N E4B** | $0.06 | - | $0.12 | 32K | FP8 |
| **LFM2-24B-A2B** | $0.03 | - | $0.12 | 32K | - |
| **Meta Llama 3 8B Instruct Lite** | $0.10 | - | $0.10 | 8K | - |
| **DeepSeek V3.1** | $0.60 | - | $1.70 | 131K | - |

> **折扣机制**：
> - **Batch inference**：最高50%折扣（固定24小时窗口，最多50,000 requests/batch，100MB/file，30B tokens/model）
> - **Cached input**：部分模型支持（如Kimi K2.6 $0.20/1M、DeepSeek-V4-Pro $0.20/1M）

#### Dedicated GPU 租赁（按小时）

| GPU类型 | 按需价格/小时 | 预留价格（7-30天） | 预留（31-90天） | 预留（91-180天） | 预留（181+天） |
|---------|-------------|-------------------|----------------|------------------|----------------|
| **HGX H100** | $3.99 | $3.59 | $3.29 | $3.09 | 联系销售 |
| **HGX H200** | $5.99 | $4.99 | $4.15 | $3.99 | 联系销售 |
| **HGX B200** | $8.19 | $7.99 | $7.79 | $6.79 | 联系销售 |
| **GB200 NVL72** | - | 联系销售 | - | - | - |
| **GB300 NVL72** | - | 联系销售 | - | - | - |

#### PTU（预留吞吐量）定价

PTU按分钟计费，价格视模型而定（如MiniMax M3: $0.05/PTU/分钟）。

#### 图像/视频/音频模型定价

Together AI也提供大量图像生成（FLUX、Imagen、Stable Diffusion）、视频（Veo、Kling、Wan）和音频模型（TTS、Whisper），价格与Fireworks类似。

#### Fine-tuning定价

| 模型大小 | LoRA SFT | Full SFT | LoRA DPO | Full DPO | 最低收费 |
|---------|----------|----------|----------|----------|----------|
| ≤16B | $0.48/1M | $0.54/1M | $1.20/1M | $1.35/1M | $4.00 |
| 17B-69B | $1.50/1M | $1.65/1M | $3.75/1M | $4.12/1M | $4.00 |
| 70-100B | $2.90/1M | $3.20/1M | $7.25/1M | $8.00/1M | $4.00 |
| DeepSeek/GLM等特定模型 | $5-$40/1M | $6-$100/1M | $12.50-$100/1M | - | $6-$60 |

### 3. Token额度与调用限制

| 层级 | 额度 | 速率限制 | 说明 |
|------|------|----------|------|
| **新用户** | 无免费tier | 动态限制 | 需最低$5充值才能开始使用 |
| **Serverless** | 按量付费 | 动态rate limits | 无固定上限，随使用量动态调整 |
| **Batch** | 最多50,000 requests/batch | 24小时窗口 | 30B tokens/model上限 |
| **Dedicated** | 按GPU/PTU预留 | 保证吞吐量 | 固定容量 |
| **Startup Accelerator** | 最高$50K free credits | 视项目而定 | 需申请 |

> **动态Rate Limits特点**：
> - Together AI使用动态rate limits，根据模型实时容量和您的最近成功使用量调整
> - 持续稳定流量会提高动态limit
> - 突发流量可能导致429（超过动态limit）或503（平台容量不足）
> - 每响应包含rate limit headers（x-ratelimit-limit等）

### 4. 过期机制
- **无免费tier**：没有月度重置的免费额度
- **充值余额**：预付费模式，未找到明确的过期时间
- **Startup credits**：未找到明确的过期时间
- **退款政策**：根据ToS，"fees paid are non-refundable"（除非适用法律要求）
- **Batch任务**：24小时窗口，超时需重新提交

### 5. API可用性
- **API Key获取**：容易，注册即可获得
- **个人用户友好度**：中等。没有免费tier，需要最低$5充值才能开始
- **Startup Accelerator**：提供最高$50K免费credit，需申请
- **OpenAI兼容**：是，支持OpenAI-compatible API

### 6. ToS相关条款（转售/共享限制）

根据 Together AI Terms of Service（2026年5月19日更新）：

> **明确禁止行为（Section 4）**：
> - "(d) transfer, distribute, resell, lease, license, or assign the Services or otherwise offer the Services on a standalone basis"
> - "(e) make calls through the API that exceed limits on the number and frequency of such calls"
> - "(c) use or access the Services to develop a product or service that is competitive with the Company’s products or services"
> - "(b) attempt to probe, scan, or test the vulnerability of the Services, breach the security or authentication measures"

> **账户责任**：
> - "You are entirely responsible for provisioning and managing your user accounts and your compliance with this Agreement"

> **费用条款（Section 6）**：
> - "payment obligations are non-cancelable and non-pro-ratable for partial months, and fees paid are non-refundable"

**转售适用性评估**：❌ **不适合**。Together AI明确禁止resell、lease、distribute、assign服务，禁止以独立方式提供服务，禁止超出API调用限制。

### 7. 模型能力关键参数

| 能力 | 详情 |
|------|------|
| **上下文长度** | 8K - 1,000K tokens（Qwen3.6 Plus支持1M） |
| **多模态** | 支持图像、视频、音频模型 |
| **推理能力** | 支持DeepSeek R1等推理模型 |
| **代码能力** | 支持Qwen3-Coder、Llama等 |
| **工具调用** | 支持Function calling（多数模型标注"Yes"） |
| **结构化输出** | 支持（多数模型标注"Yes"） |
| **嵌入** | 支持Multilingual-e5-large-instruct（$0.02/1M） |
| **微调** | 支持LoRA和Full SFT/DPO |
| **Batch推理** | 支持，最高50%折扣 |
| **Cached input** | 部分模型支持，自动应用 |
| **合规** | SOC 2 Type 2认证，HIPAA可通过BAA获得 |

### 8. 支付方式
- **信用卡**：支持全球主流信用卡
- **ACH/Wire**：支持，但需5天清算期（"Credits or prepaid balances funded via ACH, wire transfer...will not be available for use until the Company has received and confirmed clearance"）
- **账单周期**：预付费初始余额+自动充值模式
- **地区限制**：全球可用
- **企业支付**：支持定制合同和发票

---

## 五、综合对比与二手Token转售适用性评估

### 各平台关键指标对比

| 指标 | Mistral AI | Cohere | Fireworks AI | Together AI |
|------|-----------|--------|-------------|-------------|
| **免费额度** | ~10亿 tokens/月（Experiment） | 1,000 calls/月（Trial） | $1 credit | 无免费tier（需$5起充） |
| **最低消费** | 无 | 无（Production按量） | 无（$1试用后按量） | $5 |
| **最便宜模型** | $0.04/1M (Ministral 3B) | $0.0375/1M (Command R7B) | $0.03/1M (LFM2-24B) | $0.03/1M (LFM2-24B) |
| **旗舰模型价格** | $0.50-$2.00/1M | $2.50/1M | $1.74-$2.10/1M | $2.10-$3.00/1M |
| **上下文长度** | 128K-262K | 128K-256K | 8K-512K | 8K-1M |
| **Rate Limit** | 标准限制 | 500 RPM (Production) | 6,000 RPM硬上限 | 动态限制 |
| **API获取难度** | 容易 | 中等（需审批） | 容易 | 容易 |
| **OpenAI兼容** | 是 | 是 | 是 | 是 |
| **零数据保留** | Pro+可选 | 未明确 | 默认 | 未明确 |
| **显式转售禁止** | ❌ 是 | ❌ 是 | ❌ 是 | ❌ 是 |

### 二手Token转售适用性评估

| 平台 | 转售适用性 | 风险评级 | 主要障碍 |
|------|-----------|----------|----------|
| **Mistral AI** | ❌ 不适合 | 🔴 高 | ToS明确禁止sell/resell/distribute服务；禁止整合到第三方产品；Le Chat和API计费分离，无额度可转 |
| **Cohere** | ❌ 不适合 | 🔴 高 | ToS明确禁止resell/sublicense/transfer；Trial Key禁止商业用途；Production Key需组织审批 |
| **Fireworks AI** | ❌ 不适合 | 🔴 高 | ToS明确禁止buy/sell/transfer API keys；禁止resell/sublicense；预付费余额不可退款；6,000 RPM硬上限 |
| **Together AI** | ❌ 不适合 | 🔴 高 | ToS明确禁止resell/lease/distribute/assign服务；无免费tier降低套利空间；预付费不可退款 |

### 共同风险点

1. **ToS明确禁止**：所有四个平台均在ToS中明确禁止resell、sublicense、transfer、lease服务或API Key
2. **账户封禁风险**：违反ToS可能导致账户立即暂停或终止，已充值余额不可退款
3. **额度机制不适合**：
   - Mistral的免费额度是rate-limited evaluation用途
   - Cohere的Trial Key明确禁止生产/商业用途
   - Fireworks的$1 credit是starter试用
   - Together无免费tier，最低$5充值
4. **技术限制**：
   - Fireworks有6,000 RPM硬上限
   - Together是动态限制，突发流量会被限流
   - Cohere的1,000 calls/月 Trial限制极严
5. **退款风险**：所有平台均声明预付费/已付费用不可退款（除非适用法律要求）

### 结论

**四个平台均不适合作为二手Token转售的目标平台**。原因：

1. **法律/合同风险**：所有平台的ToS均明确禁止转售、再授权、转让服务或API Key，违反可能导致账户终止和法律追责
2. **商业模式不匹配**：这些平台主要按量付费（Pay-as-you-go），不存在可囤积的"月度额度"机制，没有套利空间
3. **技术限制**：Rate limits、动态限流、硬上限等机制使大规模转售技术上不可行
4. **退款风险**：预付费余额普遍不可退款，一旦账户被封，资金损失无法挽回
5. **合规成本**：企业级合规（SOC 2、HIPAA、GDPR）的审计和BAA要求进一步提高了合规门槛

---

## 六、调研局限性说明

1. **部分官网无法访问**：Mistral官方文档站点（docs.mistral.ai）和定价页面在调研期间网络访问失败，部分信息来源于第三方定价数据库（pricepertoken.com、aipricing.guru等）
2. **ToS原文获取**：Mistral和Cohere的完整ToS原文未直接获取，依赖第三方文档引用和摘要
3. **实时定价变动**：AI平台定价频繁调整，建议在实际决策前访问各平台官方定价页面确认最新价格
4. **地区政策差异**：部分平台（如Fireworks）明确中国大陆需要代理，可能影响实际可用性
5. **企业定制定价**：Enterprise级别的定价均为"联系销售"，未公开具体数字

---

> **报告生成时间**：2026年7月10日
> **数据来源**：Mistral AI官网、Cohere官网、Fireworks AI官网、Together AI官网、docs.together.ai、docs.cohere.com、pricepertoken.com、aipricing.guru、yangmao.ai等
