[中文](README.md) | **English**

# Architecture

TokenMarket is a contract-first monorepo: the Go gateway owns proxied traffic, Python services own domain and persistence, the React frontend owns presentation, and `shared/contracts` is versioned before consumers.

## Where to read

| Document | Contents |
|----------|----------|
| [overview.en.md](overview.en.md) | **As-built** V0.1 data flow (matches the code; no undeployed local Kafka) |
| [`项目开发/技术架构/`](../../项目开发/技术架构/README.md) | As-built briefing PDF (detailed) and ~2h PPT |
| [`项目开发/1-项目架构与目录结构.md`](../../项目开发/1-项目架构与目录结构.md) | Target architecture, service duties, layout (includes later-version capabilities) |
| [`项目开发/2-Go代理网关开发规范.md`](../../项目开发/2-Go代理网关开发规范.md) | Gateway implementation constraints |
| [`项目开发/3-Python后端与数据库设计规范.md`](../../项目开发/3-Python后端与数据库设计规范.md) | FastAPI / PostgreSQL / migrations |
| [`项目开发/4-前端与DevOps监控规范.md`](../../项目开发/4-前端与DevOps监控规范.md) | Frontend, CI, observability |
| [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) | Highest engineering constraint |
| [ADR index](../decisions/README.en.md) | Recorded architecture decisions |

On conflict: **constitution > accepted ADR > current `shared/contracts` > not-yet-built passages in the architecture standards**.

## Component READMEs

| Component | Notes |
|-----------|-------|
| [`services/proxy-gateway/README.md`](../../services/proxy-gateway/README.md) | Health, internal credential validation, public Chat Completions proxy |
| [`services/api-service/README.md`](../../services/api-service/README.md) | Registration, session, authorization, seller/proxy keys |
| [`services/billing-service/README.md`](../../services/billing-service/README.md) | Billing scaffold and PostgreSQL readiness |
| [`services/admin-service/README.md`](../../services/admin-service/README.md) | Admin scaffold |
| [`frontend/README.md`](../../frontend/README.md) | Web frontend |
| [`shared/README.md`](../../shared/README.md) | Contracts and validation tools |
| [`infra/README.md`](../../infra/README.md) | Compose and Grafana assets |
| [`ops/README.md`](../../ops/README.md) | Runbooks and migration ownership |
