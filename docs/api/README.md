**中文** | [English](README.en.md)

# API 导航

对外 HTTP / 事件的**权威契约在 `shared/contracts/`**，不在本目录复制一份 OpenAPI。本页只做归类，避免 `docs/api` 与 `shared/contracts` 双源漂移。

机器可读契约、owner、版本与兼容策略：[`shared/contracts/README.md`](../../shared/contracts/README.md)。

## 契约优先

新接口、事件或共享 schema 必须先在 `shared/contracts/<name>/vN/` 评审并版本化，再实现生产者或消费者。前端类型从契约生成，禁止手抄一份“刚好能跑”的模型。

- 次版本：只增加可选字段。
- 主版本：破坏字段、类型或行为。
- 弃用字段至少保留一个主版本，并标记 `deprecated`。

## V0.1 公开面

| 面 | 方法 / 路径 | 契约 |
|----|-------------|------|
| 注册 | `POST /api/v1/auth/register` | [`user-registration/v1`](../../shared/contracts/user-registration/v1/) |
| 验证码挑战 | `POST /api/v1/auth/verification-challenges` | [`phone-auth-session/v1`](../../shared/contracts/phone-auth-session/v1/) |
| 会话 | `POST /api/v1/auth/sessions`；`GET` / `DELETE /api/v1/auth/session` | 同上 |
| 授权判定 | `POST /api/v1/authorization/evaluate` | [`role-access-isolation/v1`](../../shared/contracts/role-access-isolation/v1/) |
| 卖家 Key | `/api/v1/seller-keys` | 见 `specs/008`、`specs/009`（契约随功能目录发布） |
| 买家代理 Key | `/api/v1/proxy-keys` | 见 `specs/010` |
| 公开代理 | `POST /v1/proxy/volcano/chat/completions` | [`volcano-openai-compat/v1`](../../shared/contracts/volcano-openai-compat/v1/) |
| 内部凭证验证 | `POST /internal/v1/provider-credentials/validate` | [`volcano-key-validation/v1`](../../shared/contracts/volcano-key-validation/v1/) |
| 健康 / 就绪 / metrics | `/health/live`、`/health/ready`、`/metrics` | [`repository-workflow`](../../shared/contracts/repository-workflow/) |

成功的 Chat Completions 与已开始的 SSE **保持 OpenAI 兼容形状**。管理与业务接口、以及代理**前置**失败，使用统一包络 `{code,message,data,request_id,timestamp}`。

## 所有权

- 契约由引入它的功能团队拥有；跨服务契约需要生产方与消费方同时评审。
- 生成产物提交在 `shared/contracts/`，并回指源文件。源与生成物漂移会阻断构建。

运行时行为与排障见 [`ops/runbooks/`](../../ops/runbooks/README.md)（注册、认证、授权、火山验证、火山兼容、代理告警）。
