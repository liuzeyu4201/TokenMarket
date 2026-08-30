# Phase 0 Research：统一手机号验证

## Decision 1：未知号码可投递挑战 + 补全凭证，而非 decoy 登录失败

**Decision**: `user is None` 视为注册用途：挑战保存 `phone_normalized`，dispatcher 向该号码投递 OTP。OTP 正确则消费挑战并签发 `__Host-tokenmarket_profile` 短时 cookie，响应 `PROFILE_COMPLETION_REQUIRED`。`suspended`/`deleted` 仍 decoy（无 phone_normalized、不投递、OTP 正确也不补全）。

**Rationale**: V0.1 把未知号码当 decoy 导致新用户无法验证。SF06 要求验证后补全。验证前 202 形状不变，故不破坏防枚举。

**Alternatives**: 验证前根据存在性分支 UI — 直接违反 SF06。

## Decision 2：拒绝无凭证的公开注册

**Decision**: `POST /api/v1/auth/register` 无有效补全 cookie 时 403 `AUTH_VERIFICATION_REQUIRED`。补全走 `POST /api/v1/auth/profile-completions`（可与 register 共用领域服务）。

**Rationale**: 旧接口用 `PHONE_ALREADY_REGISTERED` 枚举账号。

## Decision 3：补全与建号同事务

**Decision**: 校验 cookie → 插入 User（unique phone）→ 撤销该号码不存在的旧会话 → insert session → 标记 intent consumed。IntegrityError 则失败关闭，不把会话发给冲突方。

**Rationale**: 50 并发只一个账号。
