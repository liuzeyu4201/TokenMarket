# macOS arm64 验收证据（T070）

**状态**： **PASS**（性能测试框架 + 命名卷循环），于 Darwin arm64，Docker 29.5.3 / Compose 5.1.4 — 2026-07-22。

## 主机

| 项 | 值 |
|------|--------|
| 操作系统 | Darwin arm64 |
| 容器平台 | linux/arm64 (native) |
| Docker Engine | 29.5.3 |
| Compose | 5.1.4 |
| Node（用于 toolchain-check） | 24.18.0 via `nvm use 24.18.0` |
| Python | 3.11.15 / uv workflow project |

## 测试框架命令（已脱敏）

```text
nvm use 24.18.0
uv run --project tools/workflow python -m pytest \
  -c tools/workflow/pyproject.toml \
  tests/workflow/test_local_env_performance.py -s
```

亦为绿灯：`test_ten_down_restart_cycles_retain_named_volumes`、
`test_empty_redis_tolerance_and_no_schema_actions`。

## 结果（仅汇总）

| 检查 | 结果 |
|-------|--------|
| 冷启动批次（20 次试验） | **20/20 PASSED**；就绪检查各约 1.3–1.4s（≪ 60s 预算）；≥19 次在 60s 内 |
| 健康状态重复启动（10） | **10/10** 在 15s 内（最慢 ~0.73s）；无 registry 拉取；稳定容器/网络/卷身份 |
| 命名卷 down/restart 循环 | **PASS** |
| 空 Redis / 无 schema 动作 | **PASS** |
| 原生 arm64 镜像身份 | 经 digest 固定的拉取/启动路径演练 |
| 回环发布 | 由适配器 + compose 结构测试强制 |
| Event-v2 对等 | 单元套件 + 生命周期事件（标准封装） |

### 残留说明

`test_real_compose_ten_cycles_retain_postgres_marker` 可在并发
ADR 003 `tokenmarket-test` 部署栈占用主机端口 / 仓库标签时发生竞态。
T083 修复了部署标签分类干扰（SF02 工作区移动发现中跳过 `stack=deploy`）。
标记循环仍对主机端口占用敏感；不阻塞本主机上的 SC-001/SC-002 性能验收证据。

## 结论

macOS arm64 生命周期性能与持久化验收（T070）为
**PASS**。Linux x86_64（T069）为 **PASS**；易用性验证协议（T071）与公共
激活（T074）于 2026-07-25 完成。
