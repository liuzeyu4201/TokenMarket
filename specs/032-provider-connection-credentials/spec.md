# Feature Specification: Provider Connection 与凭据安全

**Feature Branch**: `032-provider-connection-credentials`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "V0.2 Provider Connection 与凭据安全"

**Source Feature**: `项目开发/V0.2/V0.2_0831/specs/SF14-ProviderConnection与凭据安全.md`

## Clarifications

### Session 2026-08-31

已确认决策，未向用户重复提问：

- Q: 谁能创建？ → A: 仅卖家工作区中的连接所有者。买家工作区 403。管理员 API 也不能回读明文。
- Q: 明文读回？ → A: 任何角色、任何公开 API、UI、日志、trace、事件、备份扫描路径均无明文。解密仅限代理执行路径与受控验证任务，经内部服务身份。
- Q: 加密形态？ → A: 带版本的 envelope encryption；库中仅密文、nonce、tag、密钥版本。轮换后旧密文仍可读，完成迁移后旧密钥停用。
- Q: 更新凭据？ → A: 整体替换，带版本；并发请求得到完整旧或完整新版本，不字段混搭。
- Q: SSRF？ → A: base URL 必须 HTTPS 且解析后不得为 localhost/RFC1918/link-local/元数据；禁止重定向绕过。
- Q: 删除后？ → A: 密文销毁，不可再用于新代理请求；审计保留不可逆指纹。专享 Binding 进入 degraded。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 卖家创建连接且从不回读明文 (Priority: P1)

卖家登记 OpenAI/Anthropic/Vertex 连接，提交凭据后只看到指纹与元数据。

**Why this priority**: 凭据是供给根，明文泄漏不可接受。

**Independent Test**: 创建后 GET/列表无 secret；库行无明文；日志无 secret。

**Acceptance Scenarios**:

1. **Given** 卖家工作区，**When** 以合法 provider、supply_mode 和凭据创建，**Then** 201 含 fingerprint，无 credential 字段。
2. **Given** 已创建连接，**When** GET 详情或列表，**Then** 无 secret/api_key/plaintext。
3. **Given** 买家工作区，**When** POST 创建，**Then** 403。

---

### User Story 2 - 解密最小权限与密钥轮换 (Priority: P1)

仅内部代理/验证身份可 unwrap。密钥版本轮换后新旧密文过渡可读。

**Why this priority**: 防止普通 API 变成读回通道。

**Independent Test**: 无内部令牌 unwrap 401；公开路径无 decrypt；旧 key_version 密文在 ring 中可解。

**Acceptance Scenarios**:

1. **Given** 公开会话，**When** 请求 unwrap，**Then** 未授权。
2. **Given** 内部令牌与 purpose=proxy，**When** unwrap，**Then** 得到明文且写审计（审计无明文）。
3. **Given** 以 previous key 加密的行，**When** 当前版本 ring 含 previous，**Then** 可解密。

---

### User Story 3 - SSRF 与整体替换 (Priority: P1)

非法 base URL 被拒。凭据替换原子；删除后不能再 unwrap 成功。

**Why this priority**: 防内网探测与半更新损坏。

**Independent Test**: localhost/RFC1918/link-local/metadata/redirect 均拒绝；并发替换无混搭；删除后 unwrap 失败，指纹仍在审计。

**Acceptance Scenarios**:

1. **Given** base_url 指向 127.0.0.1 或 169.254.169.254，**When** 创建，**Then** 拒绝。
2. **Given** 两并发完整替换，**When** 完成，**Then** 存储为完整旧或完整新凭据之一。
3. **Given** 已删除连接，**When** unwrap，**Then** 失败；fingerprint 仍可查询于审计元数据。

---

### User Story 4 - 卖家 UI (Priority: P2)

卖家工作区可创建连接，表单为 password 凭据，创建后不回显。买家工作区无入口。

**Independent Test**: 表单有标签；提交后页面无 secret。

**Acceptance Scenarios**:

1. **Given** 卖家工作区，**When** 打开连接页，**Then** 可创建并看到指纹。
2. **Given** 买家工作区，**When** 打开该页，**Then** forbidden。

---

### Edge Cases

- 空 secret、错误 auth 字段（Vertex 缺 project_number）→ 校验失败。
- http:// 与带 userinfo 的 URL → 拒绝。
- 平台不代理厂商 credential-management 控制面。
- 本 SF 不实现健康探测（SF15）与供给生命周期状态机全量（SF16），但删除必须 fail-closed。

## Requirements *(mandatory)*

- **FR-001**: 卖家 MUST 能创建三厂商 Connection；字段按 provider 校验。
- **FR-002**: 凭据进入服务后 MUST 立即加密；库 MUST 只存密文与密钥版本。
- **FR-003**: 解密 MUST 仅限代理执行路径和受控验证；公开/管理员 API MUST NOT 解密。
- **FR-004**: UI/公开响应 MUST 仅安全元数据与不可逆指纹。
- **FR-005**: 凭据更新 MUST 整体替换；并发 MUST NOT 字段混搭。
- **FR-006**: base URL/区域 MUST 受 SSRF allowlist 约束。
- **FR-007**: 删除后凭据 MUST NOT 用于新请求；审计 MUST 保留指纹。
- **FR-008**: 密钥轮换 MUST 支持 previous 版本过渡读取。
- **FR-009**: 买家工作区 MUST 不能写 Connection。
- **FR-010**: 不得提供厂商账号/IAM/支付控制面代理。

### Engineering Requirements

- **ER-001**: 扩展 `provider-connection/v1`（expand-only）。
- **ER-002**: CSRF；内部 unwrap 令牌。
- **ER-003**: Postgres SoR；密文列。
- **ER-004**: 领域覆盖率 ≥80%；SSRF 负向测试。

## Success Criteria

- **SC-001**: 创建后公开响应/列表/日志中明文出现次数 = 0。
- **SC-002**: 无内部令牌 unwrap 成功次数 = 0。
- **SC-003**: SSRF 用例（localhost、RFC1918、link-local、metadata、redirect）拒绝率 100%。
- **SC-004**: 并发替换后混搭凭据行数 = 0。
- **SC-005**: 删除后 unwrap 成功次数 = 0，且指纹仍可对审计。

## Assumptions

- 本地/测试用版本化密钥环模拟 KMS envelope，不接入云 KMS（无生产凭据授权）。
- SF15 将复用 unwrap purpose=verify。
- 专享 Binding 删除连接时调用既有 degrade。
