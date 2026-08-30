# ADR 005：V0.2 Endpoint Catalog 作为数据面范围唯一事实源

**状态**：Accepted
**实现验证**：Pending（本 ADR 随 `020-endpoint-catalog-governance` 落地）
**Date**: 2026-08-31
**Owner**: TokenMarket Engineering
**Deciders**: Repository maintainers / Platform team

## 背景

V0.2 承诺覆盖冻结日三厂商公开稳定模型数据面，并拒绝账号/组织/IAM/支付/凭据控制面。若范围只存在于文档散文中，Gateway、路由、计量与兼容测试会各自发明允许集合，无法证明 100% 覆盖，也无法失败关闭。

这是跨 Gateway、API、Billing、Admin 与测试的**新共享抽象**，宪章 I 要求 ADR。

## 决策

1. 在 `shared/contracts/endpoint-catalog/v1/` 提交机器可读 `catalog.json` 与 JSON Schema；人类可读 `CATALOG.md` 必须由同一 JSON 确定性生成。
2. 准入判定的权威实现放在 `services/proxy-gateway/internal/domain/endpcatalog`。Python 服务只校验 `catalog_major` 并失败关闭，不复制匹配算法。
3. 控制面必须登记为 `control_plane`（`CONTROL_PLANE_NOT_ALLOWED`）；未登记为 `ENDPOINT_NOT_CATALOGED`。
4. Preview/Beta 必须显式登记且默认拒绝，直至 Project opt-in。
5. 已发布目录只增补兼容字段；语义变化升 `catalog_major`。
6. 不把 new-api 或跨协议统一 schema 放入核心契约。V0.1 Volcano 契约保持独立。
7. Project / Provider Connection / route decision / usage / pricing / ledger / audit 的版本化契约在本决策下先行发布，领域写入仍属后续 SF。

## 备选方案

- **运行时抓取厂商 OpenAPI**：违反“不自动上线新 API”，且不稳定。
- **各服务复制目录**：必然漂移。
- **独立 catalog-service**：新网络依赖，批次 A 不需要。

## 失败模式与回滚

- 目录损坏或主版本不匹配：进程失败关闭，不服务数据面。
- 回滚：部署上一兼容主版本的目录与二进制。不兼容主版本不得 silently 加载。

## 运维成本

目录变更需要 schema 校验、评审记录、夹具版本与生成物 diff。无新数据存储。

## 后果

后续 SF18–SF21 必须消费本目录，不得另起允许列表作为发布范围。
