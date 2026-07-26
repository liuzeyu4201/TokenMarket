# Contract: Continuous Integration Quality Gate

**Version**: 1.0.0

**Adapter**: 默认 GitHub Actions；根工作流与平台无关

## Long-lived branches

| 分支 | 角色 |
|--------|------|
| `master` | 生产分支。始终可发布；生产部署的唯一源线。 |
| `master-dev` | 测试环境部署分支。集成与预生产验证先合入此处。 |

功能工作合入 `master-dev`。生产晋升是从 `master-dev`（或 hotfix PR）到 `master` 的经评审合并。分支名记录的是**代码部署线**，而非 Make 环境选择器：迁移与未来部署命令仍按 `environment-mode.md` 要求显式 `mode=local|test|prod`。

## Triggers

- 针对 `master` 或 `master-dev` 打开、重新打开、同步或以其他方式更新的 pull request。
- 推送到 `master` 或 `master-dev` 以验证最终合并提交。
- 用于安全重验的手动 `workflow_dispatch`。
- 启用 merge queue 时的 `merge_group`（针对 `master` 与 `master-dev`）。

核心门禁不使用路径过滤。同一分支上的 PR 运行可取消过期运行；对 `master` 与 `master-dev` 的 push 不得被后续 push 取消。

## Required job

- 稳定检查名：`quality-gate`。
- 项目命令：仅 `make ci`。
- 任一必需步骤失败则作业失败；无 `continue-on-error`。
- 分支保护/规则集在两个长生命周期分支上要求此检查，并阻止 force-push、删除、直接推送与绕过。

## Permissions and trust

- 工作流权限：`contents: read`；所有未列出权限为 none。
- Checkout 不持久化凭据，并获取足以进行密钥扫描的历史。
- 不受信任的 PR 代码在 `pull_request` 下运行，永不在 `pull_request_target` 下。
- 不消费仓库、组织、云或生产密钥。
- 测试仅使用合成、不可用的配置。
- 工作流不能发布包/镜像、部署、批准 PR 或写入仓库内容。
- 官方 Actions 固定到完整 commit SHA；第三方工具按校验和或容器 digest 固定。

## Blocking evidence

| 门禁 | 证据 |
|------|----------|
| Toolchains | 精确受支持版本与全部锁文件已校验 |
| Bootstrap | 冻结的 workflow/Go/Python/npm 依赖准备成功两次且不改变锁文件或解析结果 |
| Format | 非修改检查通过；干净检出保持格式幂等 |
| Type/lint/boundary | 独立 `type-check` 与聚合 lint 对每个适用组件与仓库边界通过 |
| Tests | 每个必需组件至少执行一个真实冒烟测试 |
| Contracts | schema、所有权、版本、链接与生成漂移通过 |
| Migrations | 离线校验加固定隔离 PostgreSQL 15 API→Billing 前向/回退/重试/最终 head 恢复通过 |
| Secrets/dependencies | 全历史密钥扫描与 Go/Python/npm 锁定依赖扫描通过 |
| Build | 五个不可变镜像与三个确定性资产归档构建 |
| Runtime smoke | 每个镜像以非 root 运行并变为健康；预期端点响应 |
| Image security | HIGH/CRITICAL 扫描通过，或存在有时限的已批准例外 |

## Cache policy

缓存仅包含下载内容，并按 OS、精确工具链版本与相关锁文件哈希键控。`node_modules`、虚拟环境、扫描器、构建输出、凭据与配置永不缓存。任何宽泛 restore key 不得改变依赖解析。缓存未命中仅影响速度；禁用缓存必须不改变正确性。

## Recovery and rollback

- 平台/瞬时扫描器下载失败仍计为失败，可手动重跑；允许一次有界幂等下载重试。
- 疑似缓存污染通过提升缓存 schema 或禁用缓存恢复。
- CI/工具升级回滚一并回退工作流 SHA、Make 适配器与版本来源，同时保留作业名 `quality-gate`。
- 失败的 `master` 或 `master-dev` 合并通过从最近已知绿色提交发起的经评审 revert PR 恢复；无强制 reset 或检查绕过。
- 真实密钥发现要求在任何最小、经批准的历史修复前立即撤销/轮换与使用审计。
- 抑制需要规则/漏洞 ID、分析、负责人、审批人、issue 与到期时间。
