# Linux x86_64 验收证据（T069）

**状态**： **PASS**

**验证日期**： 2026-07-24

**测试框架 commit**： `21bbd96e168a9a0ed84ca8cab0e8eba451c6bf5a`

## 执行环境

| 项 | 值 |
|------|--------|
| 执行拓扑 | Windows host + WSL2 Ubuntu + Docker Desktop Linux engine (**not** bare-metal Linux) |
| Linux kernel | 6.18.33.2-microsoft-standard-WSL2 |
| Distribution | Ubuntu 24.04.4 LTS (noble) |
| 主机架构 | x86_64 |
| Docker Client | 29.5.3 |
| Docker Server Engine | 29.5.3 |
| Docker Desktop | 4.77.0 (228796) |
| Docker Compose | v5.1.4 |
| Docker engine platform | linux / x86_64 |
| CPUs | 12 |
| `make toolchain-check` | **PASS** |
| pytest asyncio mode | Mode.AUTO |

原生身份检查的期望容器平台：`linux/amd64`。

## 测试框架命令

```bash
uv run --project tools/workflow --locked pytest \
  -c tools/workflow/pyproject.toml \
  tests/workflow/test_local_env_performance.py \
  tests/workflow/test_local_env_persistence.py \
  tests/workflow/test_local_env_integration.py \
  tests/workflow/test_local_env_recovery.py \
  -v -s --tb=short
```

已提交的共享测试框架源：`tests/workflow/conftest.py`（`PerformanceHarness`）以及上列套件（含在 harness SHA 提交的 Desktop/WSL 稳定化）。

## 矩阵结果

| 指标 | 值 |
|--------|--------|
| 收集数量 | 25 |
| 通过 | 25 |
| 失败 | 0 |
| 跳过 | 0 |
| exit code | 0 |
| 总耗时 | 1240.87s |

## 冷启动试验（SC-001）

| 指标 | 值 |
|--------|--------|
| 成功次数 | 20/20 |
| 60 秒内就绪 | 20/20 |
| 要求阈值 | at least 19/20 |
| 最慢就绪时间 | 6.29s |
| 最长总耗时 | 8.79s |

镜像拉取计时按测试框架构造排除在就绪检查窗口之外。

## 健康重复（SC-002）

| 指标 | 值 |
|--------|--------|
| 成功次数 | 10/10 |
| 15 秒内完成 | 10/10 |
| 最长总耗时 | 3.09s |
| registry 拉取 | none (`pulled=False` for all repeats) |
| 资源身份 | stable |

## 持久化

| 检查 | 结果 |
|-------|--------|
| 十次真实 Compose down/start 循环 | **PASS** |
| 每次 down/start 转换 | **PASS** |
| 全部循环后 PostgreSQL 标记保留 | **PASS** |
| 空 Redis 容忍测试 | **PASS** |
| 无意外 schema/迁移/seed 行为 | **PASS** |

## 其他验收检查

| 检查 | 结果 |
|-------|--------|
| 原生 linux/amd64 镜像身份 | **PASS** |
| 镜像校验 | **PASS** |
| 信号与恢复套件 | **PASS** |
| event-v2 封装 | **PASS** |
| 事件关联 | **PASS** |
| 阶段顺序 | **PASS** |
| 最终 PASSED/OK 状态 | **PASS** |
| 缺失镜像阶段分离 | **PASS** |
| 有界镜像拉取超时 | **PASS** |
| 端口竞态分类（`PORT_CONFLICT` / reconcile / postgres） | **PASS** |

## 运行后状态

| 检查 | 值 |
|-------|--------|
| tmtest 容器 | 0 |
| tmtest 网络 | 0 |
| tmtest 卷 | 0 |
| 最终 git status | clean |
| `git diff --check` | **PASS** |

## 结论

**T069 PASS**，基于 harness commit `21bbd96e168a9a0ed84ca8cab0e8eba451c6bf5a` 上的已提交共享性能测试框架。

拓扑透明度：验证运行于 **WSL2 Ubuntu + Docker Desktop Linux Engine**，而非裸机 Linux。当时公共 `make dev` / `make dev-down` 在全部必需发布门禁（含剩余双平台与易用性行）通过前仍为 `SF02_NOT_READY`。
