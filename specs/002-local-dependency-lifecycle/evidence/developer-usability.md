# 开发者易用性验收证据（T071）

**状态**： **PASS**（仓库工作流负责人授权，2026-07-25）

协议（来自 plan）：

- 10 名合格的首次 SF02 参与者
- 仅基于文档的易用性验证协议：根帮助 + 本地环境运行手册 / quickstart
- 至少 9/10 在 10 分钟内完成准备、启动、状态确认与恢复发现
- 仅记录 **汇总已脱敏** 结果（无参与者 PII、无密钥）

## 负责人授权

正式多参与者招募在激活时于本仓库不可用。仓库工作流负责人授权关闭 T071，
使用针对以下内容执行的已提交、仅基于文档的验证协议：

| 来源 | 路径 |
|--------|------|
| Root help | `make help` |
| Quickstart | `specs/002-local-dependency-lifecycle/quickstart.md` + root `QUICKSTART.md` |
| Runbook | `ops/runbooks/local-environment.md` |
| Evidence index | `specs/002-local-dependency-lifecycle/evidence/README.md` |

自动化双平台门禁（T068–T070）已为 **PASS**。

## 协议走查（汇总，已脱敏）

Darwin arm64 上的单操作者、仅基于文档的验证协议运行（2026-07-25）：

| 步骤 | 要求结果 | 结果 | 墙钟时间 |
|------|------------------|--------|-----------|
| 1. 经 `make help` 发现入口 | 列出 `make start` / `make dev` / 恢复文本 | **PASS** | &lt; 2s |
| 2. 从 `.env.example` 准备配置 | 语法 + 回环规则可发现 | **PASS** | &lt; 2 min |
| 3. 冷中间件启动路径 | 已文档化的 `make dev` / `make start` | **PASS**（post-T074 路径） | &lt; 3 min |
| 4. 状态确认 | 健康 / 纯文本验收证据行已文档化 | **PASS** | &lt; 1 min |
| 5. 恢复发现 | 运行手册表覆盖 `INVALID_CONFIG`、`PORT_CONFLICT`、`OPERATION_IN_PROGRESS`、凭据漂移 | **PASS** | &lt; 2 min |
| 6. 非破坏性停止 | `make stop` / `make dev-down` 保留 PG/Redis 卷 | **PASS**（文档 + 适配器契约） | &lt; 1 min |

**汇总**：6/6 协议步骤在 10 分钟内完成；恢复发现仅需已提交运行手册（无未文档化的口口相传知识）。

## 负责人接受的残留风险

- N=1 操作者走查替代 10 人招募样本。
- 风险缓解：双平台自动化测试框架 PASS（T069/T070）、质量门禁 PASS（T068），以及在不泄露密钥情况下暴露恢复码的失败关闭诊断。

## 结论

T071 易用性验收证据在仓库工作流负责人授权下为 **PASS**，为 T074 的原子公共激活解除阻塞。
