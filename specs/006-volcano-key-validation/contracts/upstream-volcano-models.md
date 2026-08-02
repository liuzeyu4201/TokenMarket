# 上游契约备忘：火山方舟 Models（实现前复核）

**Status**: 计划基线 — **实现任务必须用当期官方文档 diff 本文件**  
**Base URL (default)**: `https://ark.cn-beijing.volces.com/api/v3`  
**Auth**: `Authorization: Bearer <ARK_API_KEY>`

## 请求

```http
GET /models HTTP/1.1
Host: ark.cn-beijing.volces.com
Authorization: Bearer <redacted>
```

可配置完整 `base_url`（含区域）。超时与取消由调用 `context` 控制。

## 成功响应（预期形状 — 契约测试金标）

OpenAI-compatible 风格（实现时以官方为准锁定字段名）：

```json
{
  "object": "list",
  "data": [
    {
      "id": "doubao-pro-32k",
      "object": "model",
      "owned_by": "byteplus"
    }
  ]
}
```

**解析规则**:

- 必须存在可迭代的模型集合；元素必须含稳定字符串 `id`（或官方等价主键字段）。
- 缺失 `data` / 非数组 / 元素无 id → `invalid_response`。
- `data: []` → 认证视为通过（若 HTTP 200），随后 `supported_models=[]` →
  `no_supported_models`（在额度策略应用后的流水线中；V0.1 在额度步骤后仍会
  因 `quota_unavailable` 优先还是模型优先：见下）。

## V0.1 流水线顺序

1. platform 检查  
2. 并发闸门  
3. GET models（认证 + 模型）  
4. 额度步骤：默认 **无官方 Key 额度 API** → 直接 `quota_unavailable`  
5. 若未来启用额度且成功且 >0，再计算 allowlist 交集；交集空 → `no_supported_models`  
6. 全满足 → `success`

**优先级（当多条件同时失败）**:  
永久认证类（invalid/forbidden）> rate_limited/timeout/temporary > invalid_response >
quota_unavailable > no_supported_models > zero_quota > success。

说明：V0.1 在无额度 API 时，**成功路径 `success` 不可达**，直到额度契约启用。
自动化仍须覆盖 `success` 与 `zero_quota`（通过注入「可信额度端口」测试替身）。

## 额度端口（可选未来）

```text
type QuotaReader interface {
  ReadQuota(ctx, apiKey) (amount exact, unit string, err)
}
```

- 默认实现：`NoopQuotaReader` → 恒定 `quota_unavailable`  
- 未来官方实现：替换为真实 HTTP；契约测试金标另文  

## 错误响应

记录 status code 与脱敏 body 类别；不把 body 原文作为对外 `error_category`。  
`Retry-After` 头：秒或 HTTP-date。

## 复核记录

| Date | Reviewer | Doc URL | Delta |
|------|----------|---------|-------|
| 2026-08-01 | plan | 方舟文档中心 82379 / 社区 models 用法 | 基线：models 探活；无 Key 额度 API |
