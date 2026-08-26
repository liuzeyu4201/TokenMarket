**中文** | [English](overview.en.md)

# V0.1 现状架构

本文描述**仓库里已经跑起来的路径**，不是路线图里的完整产品图。目标架构（含后续 Kafka、MinIO、计费闭环）仍以 [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md) 为准。

## 进程与端口

本地默认由 `make start` 拉起。中间件端口只来自 `.env.local` 的 URL；应用端口可用 `*_HOST_PORT` 覆盖。

| 进程 | 默认 | 职责 |
|------|------|------|
| frontend | `:5173` | 注册、登录、工作台占位 |
| api-service | `:8000` | 用户、会话、授权、卖家 Key、买家代理 Key；内部路由查询 |
| proxy-gateway | `:8080` | 公开代理、健康、metrics；可选回环凭证验证 |
| billing-service | `:8001` | 健康 / 就绪骨架 |
| admin-service | `:8002` | 健康骨架 |
| PostgreSQL | `:5432` | 事务事实源 |
| Redis | `:6379` | 限流、会话辅助；不是唯一事实副本 |
| Grafana | `:3000` | V0.1 代理总览看板 |

## 请求路径

```text
买家 OpenAI 兼容客户端
    Authorization: Bearer <proxy key>
    POST /v1/proxy/volcano/chat/completions
                    │
                    ▼
            proxy-gateway
         ① 认证代理 Key          ──internal──► api-service /internal/v1/proxy-keys/by-hash
         ② 排除自买自卖后选 Key  ──internal──► api-service /internal/v1/seller-keys/routable
         ③ 火山方舟 Chat Completions（允许列表字段；usage 缺失不得填 0）
         ④ 用量观察 / 结构化日志 / Prometheus 指标
                    │
                    ▼
            火山方舟上游

浏览器
    /register  /login  /dashboard
                    │
                    ▼
            frontend  ──/api/v1──►  api-service
                                    POST /auth/register
                                    POST /auth/verification-challenges
                                    POST /auth/sessions
                                    /seller-keys  /proxy-keys
                                    /authorization/evaluate
```

成功的代理响应与已开始的 SSE 保持 OpenAI 形状；前置失败使用统一 `{code,message,data,request_id,timestamp}` 包络。

## 所有权

- 网关**不得**拥有用户表或卖家 Key 密文；选路通过 api-service 内部接口。
- api-service 拥有 `users`、Key 与授权审计；启动**不会**自动迁移。
- billing-service 是第二迁移所有者，V0.1 **不**扣费、不生成账单。
- 本地 Compose 只含 PostgreSQL / Redis / Grafana。Kafka 不是 SF02 依赖。

## 相关契约

- [`shared/contracts/volcano-openai-compat/v1/`](../../shared/contracts/volcano-openai-compat/v1/)
- [`shared/contracts/phone-auth-session/v1/`](../../shared/contracts/phone-auth-session/v1/)
- [`shared/contracts/user-registration/v1/`](../../shared/contracts/user-registration/v1/)
- [`shared/contracts/role-access-isolation/v1/`](../../shared/contracts/role-access-isolation/v1/)
- [`shared/contracts/local-environment/v1/`](../../shared/contracts/local-environment/v1/)
