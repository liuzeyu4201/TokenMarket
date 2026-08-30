# 硬过滤：route-decision v1.1

共享候选必须通过：mode≠dedicated、protocol、endpoint/capability、model、region、health floor、capacity/admits_new、price_valid、lifecycle、非自买自卖。

原因码：`MODE` `PROTOCOL` `ENDPOINT` `CAPABILITY` `MODEL` `REGION` `HEALTH` `CAPACITY` `PRICE` `LIFECYCLE` `SELF_TRADE` `DEDICATED`。

评分不得复活被排除连接。空集不得调用 upstream。
