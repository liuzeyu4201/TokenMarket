# Phase 0 Research

## Decision 1：三桶额度

账户、Project、Key 各自种子额度；预留取三者可用额最小值。任一层不足则整笔拒绝。

## Decision 2：hold 用追加分录表达

预留追加 `reserved` 借方；释放追加 `released` 贷方；结算先释放 hold 再追加 `settled` 三方分录。禁止改已发布分录状态来“转换”。

## Decision 3：reservation 工作行

`request_id`/`idempotency_key` 唯一约束的 reservation 行可改状态（held/consumed/released/unresolved）；它不是已发布分录。
