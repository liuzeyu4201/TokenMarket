# 卖家工作台：seller-workbench v1

- `GET /api/v1/seller/workbench` 卡片列表（卖家工作区）。
- `POST /api/v1/seller/workbench/{connection_id}/quotes` `{multiplier_bps}` 追加版本。
- `POST /api/v1/seller/workbench/{connection_id}/capacity` `{declared_capacity}` ≥0。

公开卡片不得包含 `buyer_multiplier_bps`、买家身份或请求正文。  
`admits_new` 在暂停/排空/退役或容量为 0 时为 false。  
`earnings.settled_minor` 不含 unresolved。
