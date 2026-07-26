# 验收证据：仓库工作流基线

**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14
**环境**：macOS，本地工作站

## 1. 前置条件

```bash
make help
make toolchain-check
make bootstrap
```

- `make help`：在 <2 秒内完成，列出全部公共/支持目标。
- `make toolchain-check`：对 Make、Go 1.25.12、Python 3.11.15、uv 0.11.3、
  Node 24.18.0、npm 11.16.0、Docker 29.5.3、golangci-lint 1.64.8 均 PASSED。
- `make bootstrap`：全部八个组件 PASSED；锁文件未变更。

## 2. 合成本地配置

```bash
cp .env.example .env.local
git status --short
```

- `.env.local` 未出现在 `git status` 中（已被忽略）。
- `.env.example` 仅包含名称、注释与不可用的占位符。

## 3. 成功的根级与支持动作

```bash
make fmt           # PASSED
make fmt-check     # PASSED
make type-check    # PASSED
make lint          # PASSED
make test          # PASSED
make build         # PASSED
```

- 全部八个组件均运行了真实适配器。
- 五个不可变服务镜像以版本标签构建；无 `:latest` 标签。
- 第二次 `make fmt` 未产生新的差异。

## 4. 脏工作树格式化安全性

由 `tests/workflow/test_dirty_format.py` 覆盖，并通过 `make test` 执行。
一次性仓库副本验证了 `make fmt` 会保留既有变更、未跟踪文件与范围外内容，
并在第二次运行时产生零条额外差异。

## 5. SF02 过渡行为

```bash
make dev       # FAILED with SF02_NOT_READY
make dev-down  # FAILED with SF02_NOT_READY
```

- 返回诊断码 `SF02_NOT_READY`。
- 未发生 Docker 调用、配置读取或工作树变更。

## 6. 环境模式安全性

```bash
make migrate mode=PROD   # FAILED INVALID_MODE
make migrate             # effective mode local
mode=prod make migrate   # FAILED INVALID_MODE (shell origin rejected)
make migrate mode=prod   # FAILED PROD_APPROVAL_REQUIRED
```

全部失败均发生在配置、DNS 或网络访问之前。

## 7. 迁移所有权与往返

```bash
make migrate-check              # PASSED
make migrate-integration-check  # PASSED
```

- 所有者：`api-service`，随后为 `billing-service`；`admin-service` 为非所有者。
- 每个所有者图均具有单一 head 与有效的升级/降级元数据。
- PostgreSQL 15 夹具干净地完成了前向/回退/重试/最终 head。

## 8. 路径与终端可访问性

```bash
NO_COLOR=1 make help  # plain text, no color escape codes
make test             # path fixture with spaces and CJK characters passed
```

## 9. 安全门禁

```bash
make security-check  # FAILED fail-closed: pip-audit reports starlette 0.45.3
make image-scan      # FAILED fail-closed: Trivy 0.61.0 not installed locally
```

两次失败均为环境/已知漏洞结果，而非绕过。

## 10. 完整本地 CI 门禁

```bash
make ci  # FAILED at security-check (starlette known vulnerabilities)
```

失败前的步骤：toolchain-check、bootstrap、fmt-check、type-check、
lint、test、migrate-check、migrate-integration-check 均 PASSED。build 与
runtime-smoke 在独立执行时 PASSED。

## 11. 托管 CI

- `.github/workflows/ci.yml` 存在且仅调用 `make ci`。
- 作业名 `quality-gate`，运行器 `ubuntu-24.04`，权限 `contents: read`。
- Actions 以完整 SHA 固定；`persist-credentials: false`。
- 托管运行证据将在首次 PR 合并后附加。

## 12. 未引入业务行为

- 未添加买家、卖家、提供商密钥、代理、计量、计费或管理类
  业务逻辑。
- 未触碰生产凭据、资源或部署。
