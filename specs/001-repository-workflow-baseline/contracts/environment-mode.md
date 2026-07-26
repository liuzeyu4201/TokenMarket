# Contract: Environment Mode Selection

**Version**: 1.0.0

**Applies to**: `migrate` 与所有未来部署相关命令

## Grammar

```text
mode := "local" | "test" | "prod"
```

值区分大小写。空字符串、空白变体、`dev`、`development`、`production` 以及任何未知值均无效。

## Selection rules

| 输入 | 有效结果 |
|-------|------------------|
| 无 `mode` 参数 | `local` |
| Make 命令行 `mode=local` | `local` |
| Make 命令行 `mode=test` | `test` |
| Make 命令行 `mode=prod` | `prod`，待独立审批 |
| 无命令行来源的 Shell/环境 `mode=test|prod` | 忽略为提权；有效为 `local`，或在模糊时安全失败 |
| `.env`、文件名、URL、`ENV`、`MODE` 或其他遗留信号 | 永不改变有效模式 |
| 无效/空/混合大小写的命令行值 | `INVALID_MODE`，无资源访问 |

实现检查 Make 变量来源或等效的显式调用标记。它不得使用会接受 shell 注入的 `mode` 用于非本地环境的简单默认表达式。

## Configuration mapping

模式在选择或读取真实配置引用前被校验。真实文件仍被 Git 忽略。已提交的 `.env.example` 仅包含名称、注释与不可用的合成占位符。

工作流不得将 `.env.test` 或 `.env.prod` 复制到通用 `.env`、记录已解析的连接 URL，或从现有文件推断模式。

## Production approval

`prod` 需要同时满足：

1. 显式命令行 `mode=prod`。
2. 单独的审批：
   - 交互式 TTY：用户输入精确文档化的生产确认短语。
   - 非交互：绑定到动作、commit SHA 与 run ID 的受保护环境审批证明。

缺失、过期、不匹配或未绑定的证明产生 `PROD_APPROVAL_REQUIRED`。拒绝发生在读取生产密钥、解析 DNS、探测主机、打开套接字、启动容器或修改数据之前。日志仅存储安全审批引用。

## Deployment boundary

SF01 为未来部署脚本定义并测试此选择器，但不实现云或生产部署。未来脚本必须复用本契约；不得添加替代的 `env`、`stage` 或分支推断选择器。

长生命周期 Git 分支映射到**代码部署线**，而非此选择器：

| 分支 | 部署线 |
|--------|-------------|
| `master` | 生产发布线 |
| `master-dev` | 测试环境部署线 |

未来持续交付可从这些分支*调度*作业（例如，推送到 `master-dev` 以命令行 `mode=test` 运行部署；推送到 `master` 以命令行 `mode=prod` 加审批运行部署）。Make CLI 本身仍要求显式 `mode=`，且不得读取当前 Git 分支、默认分支或远程跟踪名来选择 `local`、`test` 或 `prod`。

## Recovery

无效选择无副作用，可用显式有效值重试。失败的生产审批不被缓存。在有效选择后开始的迁移遵循经评审的负责人回退 runbook；运行中更改模式被禁止。
