# SSE 事件契约：volcano-openai-compat v1

**Contract ID**: `volcano-openai-compat/sse-events/v1`  
**Owner**: proxy-gateway  
**Consumers**: SF15（公开写回时保持这些事件语义）

## 分帧

- 事件以空行（`\n\n` 或 `\r\n\r\n`）分隔。
- 以 `:` 开头的行为注释，忽略。
- 未知 `event:` / `id:` / `retry:` 忽略。
- 一个事件内多个 `data:` 行用 `\n` 拼接后再解析。
- 事件完整前 **不得** yield；半个 UTF-8 码点留在缓冲。

## `data` 负载

1. JSON 对象 → 标准化为兼容 chunk（`object=chat.completion.chunk`），`kind=delta`。
   - 回写公开 `model`。
   - `choices[].delta` 原样语义（role/content/finish_reason/index）。
   - 忽略不影响成功形状的未知 JSON 键。
   - JSON 损坏：若尚未 yield 过 → 结构化 `invalid_response`；若已 yield → `truncated_stream`。
2. 经 trim 后等于 `[DONE]` → `kind=done`，整次流至多一次。
3. 其它非空 data → 同损坏 JSON 规则。

## 终止

| 条件 | kind | `[DONE]` |
|------|------|----------|
| 上游正常结束且发出 `[DONE]` 或等价完成 | `done` | 输出一次 |
| 上游正常结束但缺 `[DONE]`、choices 已完成 | `done` | **仍输出一次**（兼容客户端） |
| 已 yield ≥1 后断开/超时/取消/后续损坏 | `truncated` | **禁止** |
| 尚未 yield 即失败 | `error`（结构化类别） | **禁止**，且不开空流 |

「已 yield」= 适配层已向调用方交出至少一条 `kind=delta`。

## 禁止

- 为转换而 `ReadAll` 全部上游字节后再切事件。
- 在 `delta` 之后插入非 SSE 的 JSON 错误对象。
- 重复 `[DONE]`。
