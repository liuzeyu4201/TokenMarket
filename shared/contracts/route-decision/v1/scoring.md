# 综合评分：route-decision v1.2

仅对硬过滤合格集评分。policy version 不可变；变更只影响新请求。

分项整数 0–10000：

| 因子 | 高分含义 | 缺失 |
|------|----------|------|
| health | healthy=10000, degraded=5000 | 0 |
| latency | `max(0, 10000−latency_ms)` | 0 |
| capacity | `remaining×10000/declared` 封顶 10000；remaining≤0 视为耗尽 | 0 |
| price | `max(0, 20000−seller_bps)` 封顶 10000（bps 越低越好） | 0 |

`total = Σ weight_i × factor_i`。并列按 `connection_id` 升序。  
ExploreBPS=0 取最高分；>0 时用 seed 在合格集内加权抽签，不得复活硬过滤失败者。  
选择尊重 remaining 预占：remaining≤0 的连接本请求不再胜出。  
决策记录分项、胜出原因、`policy_version` 与 seed。
