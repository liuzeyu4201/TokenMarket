# 兼容策略（endpoint-catalog v1 与 V0.2 领域契约）

## 版本

- 目录 `schema_version` 1.0.0 与 `catalog_major` 独立：前者是文件格式，后者是准入语义。
- `catalog_minor` 只用于增补记录或可选字段；不得改变已有记录的 stability/stateful/path 含义。
- 改变已有记录含义、删除 stable 记录、改变错误码含义 → 新的 `catalog_major`。
- 领域 OpenAPI/事件：已发布版本只增补可选字段；破坏性变更新版本并写弃用窗口。

## 变更门禁

每次目录变更必须同时具备：

1. schema + 完整性校验通过。
2. 冻结/评审记录（来源、影响的 SF、夹具版本）。
3. 生成 `CATALOG.md` 无非确定性差异。
4. 既有合同测试夹具版本仍然可解析；删除夹具须主版本。

## 非目标

- 不自动抓取厂商 OpenAPI。
- 不把 V0.1 Volcano 契约并入本目录。
- 不引入跨协议统一请求 schema。
