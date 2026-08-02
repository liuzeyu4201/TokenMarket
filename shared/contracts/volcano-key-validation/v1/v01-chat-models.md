# V0.1 Chat Completions 模型 Allowlist

**Contract ID**: `volcano-key-validation/v01-chat-models/v1`  
**Usage**: `supported_models = intersect(upstream_ids, allowlist)`

## 默认种子（可配置覆盖）

实现可将下列 ID 作为**默认** allowlist 起点；产品变更时只改配置/本文件并加测试，
不改分类器逻辑。

| model_id（示例） | 备注 |
|------------------|------|
| `doubao-pro-32k` | 占位；以官方当期 Model ID 为准 |
| `doubao-lite-32k` | 占位 |
| `doubao-pro-128k` | 占位 |

**规则**:

- 比较前规范化：trim；大小写策略在实现中固定（建议大小写敏感，与官方 ID 一致）。
- 上游有而 allowlist 无 → 不进入 `supported_models`。
- 配置 `VOLCANO_V01_CHAT_MODELS`（逗号分隔）若非空则 **替换** 默认列表。
- 空 allowlist 配置视为配置错误：启动 fail-closed 或验证一律 `no_supported_models`
  （推荐启动时拒绝空 allowlist，避免静默全失败）。

## 测试

- 上游 `{a,b}` allowlist `{b,c}` → `supported_models=[b]`  
- 交集空 → `no_supported_models`（在额度已满足的测试替身路径下）  
