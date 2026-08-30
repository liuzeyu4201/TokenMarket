# Phase 0 Research

## Decision 1：整数 0–10000 分项

健康：healthy=10000, degraded=5000, 其它/缺失=0。  
延迟：score = max(0, 10000-latency_ms)，缺失=0。  
容量：remaining*10000/max(declared,1) 封顶 10000，缺失/0=0。  
价格：max(0, 20000-seller_bps) 封顶 10000（bps 越低越好），缺失=0。

总分 = Σ (weight_i * factor_i)；并列 connection_id 升序。

## Decision 2：探索

ExploreBPS=0 取最高分。>0 时用 seed 确定性加权抽签，仍只在合格集。
