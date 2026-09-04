**中文** | [English](README.en.md)

# API 导航

对外 HTTP / 事件的**权威契约在 `shared/contracts/`**，不在本目录复制一份 OpenAPI。本页只做归类，避免 `docs/api` 与 `shared/contracts` 双源漂移。

机器可读契约、owner、版本与兼容策略：[`shared/contracts/README.md`](../../shared/contracts/README.md)。

## 契约优先

新接口、事件或共享 schema 必须先在 `shared/contracts/<name>/vN/` 评审并版本化，再实现生产者或消费者。前端类型从契约生成，禁止手抄一份“刚好能跑”的模型。

- 次版本：只增加可选字段。
- 主版本：破坏字段、类型或行为。
- 弃用字段至少保留一个主版本，并标记 `deprecated`。

## V0.2 公开面

| 面 | 方法 / 路径 | 契约 |
|----|-------------|------|
| 注册 / 登录 / 会话 | `/api/v1/auth/*` | [`user-registration/v1`](../../shared/contracts/user-registration/v1/)、[`phone-auth-session/v1`](../../shared/contracts/phone-auth-session/v1/)、[`unified-phone-auth/v1`](../../shared/contracts/unified-phone-auth/v1/) |
| 工作区 | `POST /api/v1/auth/workspace` | [`workspace-switch/v1`](../../shared/contracts/workspace-switch/v1/) |
| 授权判定 | `POST /api/v1/authorization/evaluate` | [`role-access-isolation/v1`](../../shared/contracts/role-access-isolation/v1/) |
| Project | `/api/v1/projects` | [`project/v1`](../../shared/contracts/project/v1/) |
| Binding | `/api/v1/projects/{id}/bindings` | [`provider-binding/v1`](../../shared/contracts/provider-binding/v1/) |
| Connection | `/api/v1/connections` | [`provider-connection/v1`](../../shared/contracts/provider-connection/v1/) |
| 项目代理 Key | `/api/v1/projects/{id}/proxy-keys` | [`project-proxy-key/v1`](../../shared/contracts/project-proxy-key/v1/) |
| 原生数据面 | `/openai/*` · `/anthropic/*` · `/vertex/*` | [`native-passthrough/v1`](../../shared/contracts/native-passthrough/v1/)、[`endpoint-catalog/v1`](../../shared/contracts/endpoint-catalog/v1/) |
| 选路 | 网关内部 | [`route-decision/v1`](../../shared/contracts/route-decision/v1/) |
| 账本 / 报价 | billing-service | [`ledger/v1`](../../shared/contracts/ledger/v1/)、[`pricing/v1`](../../shared/contracts/pricing/v1/) |
| 管理面 | `/admin` + admin-service | [`admin-identity/v1`](../../shared/contracts/admin-identity/v1/)、[`admin-console/v1`](../../shared/contracts/admin-console/v1/) |
| V0.1 火山兼容 | `POST /v1/proxy/volcano/chat/completions` | [`volcano-openai-compat/v1`](../../shared/contracts/volcano-openai-compat/v1/) |
| 健康 / metrics | `/health/live`、`/health/ready`、`/metrics` | [`repository-workflow`](../../shared/contracts/repository-workflow/) |

成功的原生数据面响应保持各厂商协议形状。控制面与代理**前置**失败使用统一包络 `{code,message,data,request_id,timestamp}`。

## 所有权

- 契约由引入它的功能团队拥有；跨服务契约需要生产方与消费方同时评审。
- 生成产物提交在 `shared/contracts/`，并回指源文件。源与生成物漂移会阻断构建。

运行时行为与排障见 [`ops/runbooks/`](../../ops/runbooks/README.md)。
