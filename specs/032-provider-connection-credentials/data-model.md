# Data Model：Provider Connection

## ProviderConnection

| 字段 | 约束 |
|------|------|
| id | UUID PK |
| seller_account_id | UUID FK users |
| provider | openai \| anthropic \| vertex |
| supply_mode | shared \| dedicated |
| auth_type | api_key \| service_account |
| base_url | HTTPS，经 SSRF 校验 |
| region / location / project_number | Vertex 需要 |
| nonce, ciphertext, tag | BYTEA NULL（删除后空） |
| key_version | TEXT |
| credential_fingerprint | HEX，不可逆 |
| credential_version | INT ≥1 |
| status | active \| deleted |
| deleted_at | timestamptz NULL |

## UnwrapAudit

owner、connection_id、purpose（proxy\|verify）、request_id、outcome。无明文。

## ConnectionFact（供 Binding）

connection_id、provider、supply_mode、usable=status==active 且密文存在。
