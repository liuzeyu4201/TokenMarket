# 发布证据

**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14
**提交 SHA**：`b3c6fbef5804ff8439ab8d65885915fa4bc5cc68`

## 最终本地 `make ci`

```bash
make ci
```

结果：**在 security-check 处 FAILED**（退出码 2）

序列：

| 步骤 | 结果 |
|------|--------|
| `toolchain-check` | PASSED |
| `bootstrap` | PASSED |
| `fmt-check` | PASSED (9/9) |
| `type-check` | PASSED (9/9) |
| `lint` | PASSED (9/9) |
| `test` | PASSED (9/9) |
| `migrate-check` | PASSED |
| `migrate-integration-check` | PASSED |
| `security-check` | **FAILED** — pip-audit starlette 0.45.3 发现 |
| `build` | 未到达 |
| `runtime-smoke` | 未到达 |
| `image-scan` | 未到达 |

该失败是 `security-evidence.md` 中已文档化的已知 fail-closed 结果。
未引入业务逻辑或意外的工作树漂移。

## 不可变产物

### 容器镜像

| 组件 | 镜像标签 |
|-----------|-----------|
| proxy-gateway | `tokenmarket/proxy-gateway:0.1.0` |
| api-service | `tokenmarket/api-service:0.1.0` |
| billing-service | `tokenmarket/billing-service:0.1.0` |
| admin-service | `tokenmarket/admin-service:0.1.0` |
| frontend | `tokenmarket/frontend:0.1.0` |

### 资产归档

| 组件 | 归档 | SHA-256 |
|-----------|---------|---------|
| shared | `shared/dist/shared-assets.tar.gz` | 每次构建确定性 |
| infra | `infra/dist/infra-assets.tar.gz` | 每次构建确定性 |
| ops | `ops/dist/ops-assets.tar.gz` | 每次构建确定性 |

## 托管 `quality-gate`

- 工作流：`.github/workflows/ci.yml`
- 作业名：`quality-gate`
- 唯一项目命令：`make ci`
- PR 与最终 `master` / `master-dev` 提交的托管运行 URL 将在首次
  合并的 PR 后附加。

## 上线 / 回滚说明

- CI 适配器轻薄且可替换；项目逻辑保留在根
  Makefile 与 `tools/workflow/` 中。
- 对损坏的 CI 变更进行回滚时，使用经评审的 revert PR，并由同一
  `quality-gate` 保护。
- `starlette` 依赖发现必须在托管门禁变绿之前
  得到解决或正式例外。
