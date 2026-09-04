**中文** | [English](overview.en.md)

# V0.2 现状架构

本文描述**仓库里已经跑起来的路径**，不是路线图里尚未落地的资金闭环。目标架构（含后续 Kafka、MinIO、真实支付）仍以 [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md) 为准。版本范围见 [`项目开发/V0.2/V0.2_0831/README.md`](../../项目开发/V0.2/V0.2_0831/README.md)。

## 进程与端口

本地默认由 `make start` 拉起。中间件端口只来自 `.env.local` 的 URL；应用端口可用 `*_HOST_PORT` 覆盖。

| 进程 | 默认 | 职责 |
|------|------|------|
| frontend | `:5173` | 注册、登录、Project / Binding / Connection、卖家供给、`/admin` |
| api-service | `:8000` | 用户、会话、授权、Project、Binding、Connection、代理 Key；内部路由快照 |
| proxy-gateway | `:8080` | 原生透传、火山兼容入口、健康、metrics |
| billing-service | `:8001` | 测试额度账本、报价、对账 |
| admin-service | `:8002` | 独立管理员会话与运维面 |
| PostgreSQL | `:5432` | 事务事实源 |
| Redis | `:6379` | 限流、会话辅助；不是唯一事实副本 |
| Grafana | `:3000` | 代理与 SLO 看板 |

## 请求路径

```text
买家原生 SDK
    Authorization: Bearer <tmk-… 代理 Key>
    /openai/*  |  /anthropic/*  |  /vertex/*
                    │
                    ▼
            proxy-gateway
         ① 认证代理 Key + Project 快照  ──internal──► api-service
            /internal/v1/proxy-keys/by-hash
            /internal/v1/projects/{id}/route-snapshot
         ② 目录准入（稳定端点；Preview 须 Project preview_opt_in）
         ③ 共享：硬资格过滤 → 评分选路；专享：独占连接，失败关闭
         ④ 同协议透传到上游；优先记录上游花费，否则用量×费率
         ⑤ 无法确定的费用 → unresolved，永不记 0
                    │
                    ▼
            OpenAI / Anthropic / Vertex

V0.1 兼容入口仍可用：
    POST /v1/proxy/volcano/chat/completions  →  火山方舟 OpenAI 兼容 Chat Completions

浏览器
    /register  /login  /projects  /connections  /supply  /admin/login
                    │
                    ▼
            frontend  ──/api/v1──►  api-service
                                    /auth/*  /projects  /bindings
                                    /connections  /proxy-keys
            /admin/*  ────────────►  admin-service（独立 Cookie）
```

成功的数据面响应保持各厂商原生形状。控制面与代理**前置**失败使用统一 `{code,message,data,request_id,timestamp}` 包络。

## 所有权

- 网关**不得**拥有用户表或 Connection 明文；选路通过 api-service 内部快照。
- Project 模式与 `preview_opt_in` 来自已认证 Project 记录，**不**来自请求头。
- api-service 拥有 `users`、Project、Binding、Connection 密文与授权审计；启动**不会**自动迁移。
- billing-service 拥有测试额度账本；V0.2 **不**充值、不提现、不法币锚定。
- 本地 Compose 只含 PostgreSQL / Redis / Grafana。Kafka 不是 SF02 依赖。

## 相关契约

- [`shared/contracts/native-passthrough/v1/`](../../shared/contracts/native-passthrough/v1/)
- [`shared/contracts/endpoint-catalog/v1/`](../../shared/contracts/endpoint-catalog/v1/)
- [`shared/contracts/project/v1/`](../../shared/contracts/project/v1/)
- [`shared/contracts/provider-binding/v1/`](../../shared/contracts/provider-binding/v1/)
- [`shared/contracts/provider-connection/v1/`](../../shared/contracts/provider-connection/v1/)
- [`shared/contracts/route-decision/v1/`](../../shared/contracts/route-decision/v1/)
- [`shared/contracts/ledger/v1/`](../../shared/contracts/ledger/v1/)
- [`shared/contracts/phone-auth-session/v1/`](../../shared/contracts/phone-auth-session/v1/)
- [`shared/contracts/volcano-openai-compat/v1/`](../../shared/contracts/volcano-openai-compat/v1/)
