# ledger v1

Version: 1.1.0（SF28 测试额度预留与同步结算）

- [ledger-entry.schema.json](./ledger-entry.schema.json)

分录只追加。reservation 按 request/idempotency 唯一。已知成本同步平衡结算：buyer debit = seller earning + spread。未知成本进入 unresolved，不得记 0、不得盲目释放。无充值、提现、法币锚定。
