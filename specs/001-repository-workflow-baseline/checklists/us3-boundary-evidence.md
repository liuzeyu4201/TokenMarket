# US3 边界证据

**功能**：specs/001-repository-workflow-baseline — 仓库工程工作流基线
**故事**：US3 — 在明确的组件边界内开始开发
**记录日期**：2026-07-15

## 1. 结构测试

`tests/workflow/test_structure.py` 验证：

- 每个组件都有非空的 `README.md`。
- 组件路径保持在仓库根目录内。
- 已声明的 `test_root` 目录存在。
- 交付物属于已知产物类型之一。

结果：**4 通过，0 失败**。

## 2. 契约测试

`tests/workflow/test_contracts.py` 验证：

- `shared/contracts/_meta/contract-manifest.schema.json` 存在。
- `shared/contracts/repository-workflow/v1/` 中的每个运行时契约均携带
  `$schema` 与 `schema_version`。

结果：**2 通过，0 失败**。

## 3. 边界测试

`tests/workflow/test_boundaries.py` 验证：

- `admin-service` 不绑定 `migrate` 动作。
- 没有 Python 服务导入另一服务的内部包。

结果：**2 通过，0 失败**。

## 4. ADR 策略测试

`tests/workflow/test_adr_policy.py` 验证：

- `docs/decisions/` 存在。
- `docs/decisions/README.md` 存在且非空。
- `docs/decisions/001-github-actions-ci-adapter.md` 存在。

结果：**3 通过，0 失败**。

## 5. 代码所有者

`.github/CODEOWNERS` 将评审所有者分配给：

- 根工作流、CI 与 `CODEOWNERS` 自身
- 每个服务边界
- `shared/` 契约与校验
- `infra/` 与 `ops/` 平台资产
- 安全敏感配置文件

## 6. 组件 README

全部八个组件目录均包含文档化所有权、
职责与允许依赖的 README：

- `services/proxy-gateway/README.md`
- `services/api-service/README.md`
- `services/billing-service/README.md`
- `services/admin-service/README.md`
- `frontend/README.md`
- `shared/README.md`
- `infra/README.md`
- `ops/README.md`

## 7. 签核

US3 实现证明每个资产都有唯一正确位置、
跨服务边界得到强制执行、契约已版本化，且未来结构变更
需要 ADR。
