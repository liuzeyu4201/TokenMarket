# US2 安全证据

**功能**：specs/001-repository-workflow-baseline — 仓库工程工作流基线
**故事**：US2 — 安全地准备本地配置
**记录日期**：2026-07-15
**环境**：macOS, Go 1.25.12, Python 3.11.15, Node 24.18.0, Docker Desktop

## 1. Git 忽略规则

`.gitignore` 拒绝本地配置与密钥，同时允许安全的示例
定义：

```text
.env
.env.*
!.env.example
!.env.*.example
```

由 `tests/workflow/test_configuration.py` 验证：

- `test_gitignore_rejects_env_files` PASSED
- `test_gitignore_allows_example_definitions` PASSED

## 2. `.env.example` 配置定义

根 `.env.example` 仅以安全占位符声明 SF01 变量：

| 变量 | 用途 | 敏感 | 占位符 |
|----------|---------|-----------|-------------|
| `MODE` | 运行模式 | No | `local` |
| `DATABASE_URL` | PostgreSQL 连接 | Yes | `postgresql://app:replace-me@localhost:5432/tokenmarket` |
| `ADMIN_DATABASE_URL` | 预留管理库 URL | Yes | 同一安全占位符 |
| `REDIS_URL` | 为 SF02 预留 | No | `redis://localhost:6379/0` |
| `KAFKA_BROKERS` | 为 SF02 预留 | No | `localhost:9092` |
| `AI_GATEWAY_URL` | 为 SF02 预留 | No | `https://api.example.local` |
| `AI_GATEWAY_KEY` | 为 SF02 预留 | Yes | `sk-replace-me` |

不存在真实地址、密码或提供商密钥。

## 3. 配置预检

`tools/workflow/security.py::validate_config` 在任何持久副作用之前拒绝
缺失、空、类型错误与危险默认值。错误消息
仅暴露变量名。

测试证据（`tests/workflow/test_config_preflight.py`）：

- `test_missing_required_variable_fails` PASSED
- `test_empty_required_variable_fails` PASSED
- `test_wrong_type_variable_fails` PASSED
- `test_dangerous_production_default_fails` PASSED
- `test_valid_local_config_passes` PASSED

## 4. 脱敏

`tools/workflow/security.py::redact` 移除类密钥值，同时保留
变量名。模式覆盖：

- `sk-*` API 密钥
- `api_key`、`secret`、`token`、`password` 赋值
- `Bearer` 令牌

测试证据（`tests/workflow/test_redaction.py`）：**9 通过，0 失败**。

## 5. 密钥扫描

`make security-check` 对完整 Git 历史调用 `gitleaks detect`。
合成夹具测试（`tests/workflow/test_secret_scan.py`）在未安装
`gitleaks` 的主机上跳过；本主机可用 `gitleaks` 8.24.0，扫描会运行。

## 6. 依赖扫描

`make security-check` 运行：

- 对 `services/proxy-gateway` 的 `govulncheck`
- 对导出的 `services/api-service` 需求的 `pip-audit`
- 在 `frontend` 中的 `npm audit --audit-level=moderate`

已安装扫描器版本：

| 扫描器 | 版本 |
|---------|---------|
| gitleaks | 8.24.0 |
| govulncheck | 1.1.4 |
| pip-audit | 2.10.1 |
| npm audit | 11.16.0 |

### 已知发现

`pip-audit` 报告 `starlette 0.45.3`（FastAPI 0.115.8 的传递依赖）中的
已知漏洞。示例公告：`PYSEC-2026-161`。扫描按要求
fail-closed；修复跟踪为后续依赖升级，
超出 SF01 准备扫描门禁本身的范围。

## 7. Dockerfile 构建卫生

全部五个 Dockerfile：

- 不接受密钥构建参数。
- 不将 `.env*` 文件复制进镜像。
- 以非 root 用户运行服务。
- 不留下敏感构建层产物。

## 8. 运行手册

`ops/runbooks/workflow.md` 文档化了：

- 本地配置工作流：复制 `.env.example` → `.env.local`。
- 密钥发现响应：吊销/轮换、审计、开立跟踪 issue。
- 带负责人、审批人、issue 与过期字段的例外格式。

## 9. 签核

US2 实现提供了安全的本地配置准备、密钥
脱敏、fail-closed 安全扫描与文档化的例外处理。
这一项未关闭的依赖发现表明扫描器正在工作，并将
通过正常的依赖更新工作流修复。
