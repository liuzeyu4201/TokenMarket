# 本地环境运行手册（runbook / SF02）

Owner：repository workflow owner

公共入口：`make dev`、`make dev-down`（仅中间件）以及
`make start` / `make stop`（中间件 + 主机应用进程）。SF02
公共激活已在 T074 完成；见
`specs/002-local-dependency-lifecycle/evidence/README.md`。

## 安全检查

- 优先使用根目录 Make 目标与工作流事件；不得把密钥复制进 shell 历史。
- 用精确的 Compose 项目标签检查本项目容器
  （`com.docker.compose.project=tokenmarket-<hash>`）。切勿用工作区路径过滤。
- 命名卷 `*_postgres-data` 与 `*_redis-data` 在普通 `dev-down` 后仍保留。
  Grafana 仅使用 tmpfs。

## 常见恢复

| 症状 | 处理 |
|---------|--------|
| `INVALID_MODE` | 仅在命令行省略 mode 或使用 `mode=local` |
| `INVALID_CONFIG` | 在被忽略的 `.env.local` 中修正字段**名**（切勿把密钥贴进工单） |
| `PORT_CONFLICT` | 释放回环端口，或只修改对应 URL 中的端口 |
| `OPERATION_IN_PROGRESS` | 等待另一生命周期操作结束；重试同一命令 |
| `DEPENDENCY_NOT_READY` / 超时 | 检查仍保留的容器；修复认证/运行时后重跑 `make dev` |
| `RESOURCE_OWNERSHIP_CONFLICT` | 不得接管他方资源；使用拥有该资源的工作区 |
| 工作区路径已移动 | 从原路径身份恢复；仅报告的资源不会被新路径停止 |
| 启动/停止被中断 | 重跑同一目标；状态保留以便直接收敛 |
| PostgreSQL 卷凭据漂移 | 无配置时 stop 仍安全；凭据与卷匹配前 start 失败关闭（fail-closed） |

## 非破坏性停止

`make dev-down` 仅停止并移除精确匹配项目的容器与网络，
带 `--remove-orphans`，且**不得**传入 `--volumes`、`--rmi` 或 prune。
已停止时重复 stop 为幂等成功。

## 可访问性

工作流输出为兼容 `NO_COLOR` 的纯文本或 JSONL，无图标或交互提示。
仅凭退出状态即可判断成功/失败。

## 验收证据责任

跨平台性能、持久化、恢复与易用性验收证据，在自动化门禁通过后，
由工作流负责人记录在 `specs/002-local-dependency-lifecycle/evidence/`。
