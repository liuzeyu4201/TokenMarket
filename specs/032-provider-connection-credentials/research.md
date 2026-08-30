# Phase 0 Research：Provider Connection

## Decision 1：扩展既有 `provider-connection/v1`

**Decision**: 1.1.0 expand-only，不新建 catalog 目录。

## Decision 2：复用 CredentialEncryptor

**Decision**: 与卖家 Key 同一 envelope（nonce/ciphertext/tag + key_version ring）。`SELLER_KEY_MATERIAL` / previous 即本地 KMS 接口。

**Rationale**: 宪章要求 AEAD/认证加密与可测轮换；不引入新依赖。

## Decision 3：公开 API 永不 decrypt

**Decision**: 列表/详情/替换响应只有 fingerprint。`POST /internal/v1/provider-connections/{id}/unwrap` 需内部令牌。

## Decision 4：SSRF 在写入时解析

**Decision**: HTTPS-only；拒绝 loopback/RFC1918/link-local/ULA/metadata host；解析全部 A/AAAA，任一私网即拒绝。Redirect：校验 Location 同样规则且默认不跟随。

## Decision 5：整体替换用 credential_version

**Decision**: `UPDATE … WHERE credential_version=:expected`。失败 409。新行完整密文，旧密文列被覆盖。

## Decision 6：删除 wipe 密文

**Decision**: ciphertext/nonce/tag 置空，status=deleted，fingerprint 保留。ConnectionLookup.usable=false；调用 BindingService.degrade_for_connection。
