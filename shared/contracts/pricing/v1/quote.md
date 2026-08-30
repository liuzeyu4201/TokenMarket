# 报价：pricing v1.1

```
base = reported_cost_minor_units   # 若 SF26 选择 reported
     | Σ usage_dim × rate_minor_units
buyer_debit     = half_up(base × buyer_bps / 10000)
seller_earning  = half_up(base × seller_bps / 10000)
spread          = buyer_debit - seller_earning  # MUST ≥ 0
```

无适用费率 → unresolved，不得猜价。  
请求接受时锁定 `(rate_version, buyer_bps, seller_bps)`。published 不可原地修改。
