# Usage 观察契约：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/usage-observation/v1`  
**Owner**: proxy-gateway  
**Consumer**: SF17（本功能不落账、不估算）

## 字段

| Field | Type | 完整时 |
|-------|------|--------|
| `prompt_tokens` | integer ≥ 0 | 必有 |
| `completion_tokens` | integer ≥ 0 | 必有 |
| `total_tokens` | integer ≥ 0 | 必有 |
| `status` | `complete` \| `missing` \| `inconsistent` | 必有 |
| `source` | `upstream` | 必有（本功能固定） |

禁止 IEEE754 二进制浮点表示 token 计数。

## 判定

1. 三分项均缺失或不存在 usage 对象 → `missing`；usage 对象不出现或全字段 omit。**禁止** `{0,0,0}`。
2. 任一分项缺失、类型非整数、或为负 → `missing` 或 `inconsistent`（负数为 `inconsistent`）。
3. 三分项均为非负整数且 `total_tokens >= prompt_tokens + completion_tokens` → `complete`。
4. 三分项均为非负整数且 `total_tokens < prompt_tokens + completion_tokens` → `inconsistent`；保留原始整数，**不得**改写。

## 与成功对象的关系

- 非流式：`choices` 可读 ⇒ 仍 `error_category=success`，无论 usage status。
- 流式正常结束 ⇒ 仍 `kind=done`，末块可带不完整 usage。
- 本层 `source` 只为 `upstream`。估算与 `not_available` 落账属 SF17。
