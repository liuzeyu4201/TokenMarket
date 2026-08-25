# 上游契约备忘：火山方舟 Chat Completions（实现前复核）

**Status**: 计划基线 — **实现任务必须用当期官方文档 diff 本文件**  
**Base URL (default)**: `https://ark.cn-beijing.volces.com/api/v3`  
**Auth**: `Authorization: Bearer <ARK_API_KEY>`

## 请求

```http
POST /chat/completions HTTP/1.1
Host: ark.cn-beijing.volces.com
Authorization: Bearer <redacted>
Content-Type: application/json
Accept: application/json
```

流式时 `Accept: text/event-stream`，body 含 `"stream": true`。

可配置完整 `base_url`（含区域）。超时与取消由 `context` 控制。

## 成功响应形状（非流式 — 契约测试金标）

OpenAI-compatible：

```json
{
  "id": "chatcmpl-synthetic",
  "object": "chat.completion",
  "created": 1710000000,
  "model": "doubao-pro-32k",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "hello" },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 2,
    "total_tokens": 10
  }
}
```

解析规则：

- `choices` 必须为非空数组，否则 `invalid_response`。
- `choices[].message` 可读即可；content 原样进入兼容结果。
- `usage` 按 usage-observation 契约；缺失不否定成功。
- 额外未知键忽略。

## 流式

SSE `data: {chunk json}` … `data: [DONE]`。chunk 的 `object` 通常为
`chat.completion.chunk`，`choices[].delta` 承载增量。

## 错误响应

记录 status 与脱敏 body 类别。`Retry-After`：秒或 HTTP-date。

方舟扩展（如 `thinking`）**不**在 V0.1 出站允许列表。

## 复核记录

| Date | Reviewer | Doc URL | Delta |
|------|----------|---------|-------|
| 2026-08-24 | plan | 方舟 82379/1494384 Chat API；82379/1330626 OpenAI SDK 兼容 | 基线：`POST /api/v3/chat/completions`；Bearer；content 可为 string 或 parts；与 SF06 同一 Base URL |
