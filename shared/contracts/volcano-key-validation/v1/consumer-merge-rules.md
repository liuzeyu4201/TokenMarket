# 调用方合并规则：SF06 结果 → 持久认证/健康事实

**Contract ID**: `volcano-key-validation/consumer-merge/v1`  
**Applies to**: SF08、SF16 及任何持久化 SF06 结果的组件  
**Producer**: SF06 仅保证单次 `error_category` 正确；**不**执行合并

## 强制规则

1. **永久无效写入**  
   仅当 `error_category ∈ {invalid, forbidden}` 时，调用方 **MAY** 将持久认证/健康
   事实更新为「凭证永久无效 / 需更换 Key」类状态。

2. **禁止误杀**  
   当 `error_category ∈ {rate_limited, temporary_unavailable, timeout,
   quota_unavailable, no_supported_models, invalid_response}` 时，调用方
   **MUST NOT** 仅凭该次结果将既有「认证有效」覆盖为永久 `invalid`。

3. **success**  
   可更新额度、模型列表、`last_validated_at` 与健康为可路由（若其他门禁满足）。

4. **zero_quota**  
   可标记不可路由/不可接入，但 **MUST NOT** 等同于认证 `invalid`（除非产品另有
   明确规则且单独评审）。

5. **quota_unavailable（V0.1 默认主路径）**  
   - 不得当作 `zero_quota`；  
   - 不得当作 `success`；  
   - 接入门禁若要求 `remaining_quota > 0`，则应 **拒绝接入** 并返回可区分错误，
     而非写入零额度。

6. **并发**  
   多次 SF06 调用互不覆盖彼此内存；持久层合并使用「最新 checked_at + 上表规则」。

## 验收

SF06 包内：分类表驱动 100%。  
SF08/SF16：夹具「先 success 后 rate_limited」持久 invalid 写入次数 = 0（SC-004）。
