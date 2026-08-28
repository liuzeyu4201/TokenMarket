# Security Policy / 安全策略

**中文** | [English below](#english)

TokenMarket 处理第三方提供商凭证与计价值记录。安全默认失败关闭。

## 报告问题

通过内部工程渠道报告安全问题（不要在公开 Issue 中粘贴密钥、Cookie、上游 Key 或用户数据）。

已知泄露时：

1. 立即吊销或轮换该凭据。
2. 用提供商日志审计使用情况。
3. 开可跟踪工单，写明负责人、审批人与到期日。

细则：[`ops/runbooks/workflow.md`](ops/runbooks/workflow.md)。

## 仓库约束

- 真实配置只放在被 Git 忽略的 `.env.local`；[`.env.example`](.env.example) 仅含不可用占位符。
- 不得提交提供商 Key、会话 Cookie、生产数据或未脱敏日志。
- `make ci` 中的 gitleaks、govulncheck、pip-audit、npm audit 失败关闭。
- 生产动作必须显式 `mode=prod` 并持有由另一名授权主体签发的短时绑定审批证明（禁止操作者自批，禁止仅凭确认短语授权）。
- 卖家上游 Key 使用认证加密；比较、轮换、吊销与脱敏路径必须可测。

---

<a id="english"></a>

## English

TokenMarket handles third-party provider credentials and value-bearing records. Security fails closed by default.

### Reporting

Report security issues through internal engineering channels. Do not paste secrets, cookies, upstream keys, or user data into public issues.

If a secret is already exposed:

1. Revoke or rotate it immediately.
2. Audit use in provider logs.
3. Open a tracked ticket with owner, approver, and due date.

Details: [`ops/runbooks/workflow.md`](ops/runbooks/workflow.md).

### Repository rules

- Real config lives only in gitignored `.env.local`; [`.env.example`](.env.example) holds unusable placeholders.
- Do not commit provider keys, session cookies, production data, or unredacted logs.
- gitleaks, govulncheck, pip-audit, and npm audit in `make ci` fail closed.
- Production actions require explicit `mode=prod` and a short-lived approval proof issued by a separately authenticated authorized principal. Self-approval and phrase-only confirmation are not authorization.
- Seller upstream keys use authenticated encryption; compare, rotate, revoke, and redact paths must be testable.
