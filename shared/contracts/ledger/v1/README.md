# ledger v1

Version: 1.2.0（SF29 异步对账与未决）

- [ledger-entry.schema.json](./ledger-entry.schema.json)
- [unresolved-case.schema.json](./unresolved-case.schema.json)
- [recon-ticket.schema.json](./recon-ticket.schema.json)

分录只追加。reservation 按 request/idempotency 唯一。已知成本同步平衡结算：buyer debit = seller earning + spread。未知成本进入 unresolved，不得记 0、不得盲目释放。迟到 reported 只追加差额。无充值、提现、法币锚定。

