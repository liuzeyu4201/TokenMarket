# ops/

运维资产：迁移所有权登记、监控 / 备份 / 运行手册（runbook），以及工作流工具。
SF01 校验这些资产并以确定性方式打包。

## 本地环境（SF02）

- 清单：`ops/workflow/local-dependencies.json`（PostgreSQL 15.18、Redis 7.2、
  Grafana OSS 13.0；仅多平台 digest）。
- 运行手册：[`runbooks/local-environment.md`](runbooks/local-environment.md)。
- 公共入口 `make dev` / `make dev-down` 已在 T074 激活：在受支持主机上管理
  PostgreSQL / Redis / Grafana 的真实本地生命周期（非破坏性 down，保留命名卷）。
  日常开发默认还可使用 `make start` / `make stop`（中间件 + 五个主机应用进程）。
  历史诊断码 `SF02_NOT_READY` 不再是正常启动主路径。
- SF02 支持的主机平台：macOS arm64 与 Linux x86_64。
- 业务服务不由 `make dev` 启动；本功能中仅 API Service 与 Billing Service
  实现 PostgreSQL 就绪检查探针。

## 部署栈（ADR 003）

- Compose 分层：`infra/docker/compose.middleware.yml`、`compose.app.yml`、
  `compose.deploy.yml`（切勿把业务服务扩进 `compose.local.yml`）。
- 契约：`shared/contracts/deploy-environment/v1/lifecycle.md`。
- 运行手册：[`runbooks/deploy.md`](runbooks/deploy.md)。
- 公共入口 `make deploy` / `make deploy-down` 必须显式 `mode=test|prod`，
  在部署适配器落地前保持失败关闭（fail-closed）。
