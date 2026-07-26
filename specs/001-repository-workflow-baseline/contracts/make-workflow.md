# Contract: Root Make Workflow

**Version**: 1.0.0

**Owner**: 仓库维护者

**Audience**: 开发者、CI 适配器与未来组件维护者

## Invocation

所有公共动作通过仓库根 Makefile 从任意工作目录调用。文档示例使用仓库根：

```text
make <target> [mode=local|test|prod]
```

工作流从自身位置解析路径。支持含空格或非 ASCII 字符的仓库路径。公共成功语义为 `0 = success`；任何非零结果为失败。精确的非零数值不是稳定 API，因为 Make 可能规范化子进程退出值。

## Public targets

| 目标 | 用途 | 副作用 | 成功证据 | 必需失败行为 |
|--------|---------|--------------|------------------|---------------------------|
| `help` | 显示命令、前置条件、副作用与恢复 | 无 | 全部公共与稳定支持目标已文档化；2 秒内完成 | help 本身不得运行预检或变更状态 |
| `dev` | SF02 后启动本地依赖 | SF02 后的本地资源 | SF01：永不成功；SF02 将定义健康证据 | SF02 前发出 `SF02_NOT_READY`，不执行 Docker/配置/网络动作，返回非零 |
| `dev-down` | SF02 后停止本地依赖且不删除持久数据 | SF02 后的本地资源 | SF01：永不成功；SF02 将定义停止证据 | 与 `dev` 相同的 SF01 阻塞行为；未来正常停止不得删除卷 |
| `fmt` | 应用仓库格式化器 | 已声明的源/配置文件 | 每个必需组件运行了真实格式化器；第二次运行不增加差异 | 永不 reset、delete、stash、checkout 或修改声明范围外内容 |
| `lint` | 静态、类型、边界与契约校验 | 除已声明缓存外无 | 每个必需组件产生真实报告 | 缺失组件、工具、适配器或必需检查使聚合失败 |
| `test` | 运行全部组件与工作流测试 | 临时测试资源/工件 | 每个必需组件报告至少一个已执行测试 | 零测试、跳过的必需套件或组件失败使聚合失败 |
| `build` | 构建五个服务镜像与三个确定性资产包 | 构建工件与本地镜像 | 不可变标签镜像与可复现资产归档存在 | 缺失锁文件、跨上下文复制、root 镜像或不可复现资产失败 |
| `migrate` | 将经评审的负责人迁移应用到所选外部环境 | 持久数据库状态 | 报告负责人顺序与 applied/pending 计数 | 连接前校验 mode/审批/配置；永不启动 DB；部分失败非零并带回退引用 |

## Supporting targets

| 目标 | 契约 |
|--------|----------|
| `bootstrap` | 在 `toolchain-check` 之后，仅为工作流工具与适用组件准备已提交锁解析的项目依赖；永不安装系统工具、重写锁或推断新版本；第二次运行为解析幂等 |
| `type-check` | 运行完整可独立调用的 Go/Python/TypeScript type-check 集合；`lint` 也聚合同一集合，而非定义第二套实现 |
| `toolchain-check` | 在副作用前校验工具、版本、锁文件与完整性引用 |
| `fmt-check` | 供日常使用与 CI 预检的非修改格式化检查 |
| `structure-check` | 对账组件清单、路径、负责人、测试、适配器与允许的依赖 |
| `contracts-check` | 校验契约 schema、版本、所有权、链接与生成漂移 |
| `migrate-check` | 离线图/负责人/回退校验；CI 可增加隔离 PostgreSQL 前向/回退证据 |
| `migrate-integration-check` | 仅启动带合成凭据的固定隔离 PostgreSQL 15 容器，按 API 然后 Billing 运行前向/回退/重试/最终 head 恢复，并丢弃 fixture；永不调用 `dev` 或接触共享数据库 |
| `security-check` | 密钥与锁定依赖扫描；扫描器/数据库失败时失败关闭 |
| `image-scan` | 扫描 `build` 产生的不可变镜像；除非存在已批准例外，否则阻塞 HIGH/CRITICAL |
| `ci` | 以稳定顺序执行完整必需门禁；是 CI YAML 中的唯一项目命令 |

## Aggregate execution

1. 解析仓库根，不依赖调用者 `pwd`。
2. 校验动作语法与环境模式。
3. 在副作用前运行工具链/配置预检。
4. 加载单一组件清单。
5. 按清单顺序执行必需组件动作并快速失败。
6. 发出安全步骤事件与最终聚合事件。
7. 仅当每个必需步骤产生其必需证据时返回 `0`。

当必需步骤失败时，其余必需步骤为带失败原因的 `SKIPPED`；它们永不被报告为通过。修复原因后重跑必须安全。

## CI aggregate order

`make ci` 执行：

1. `toolchain-check`
2. `bootstrap`
3. `fmt-check`
4. `type-check`
5. `lint`（含结构与契约检查，并复用同一 type-check 实现）
6. `test`
7. `migrate-check`
8. `migrate-integration-check`
9. `security-check`
10. `build`
11. container health smoke
12. `image-scan`

CI 适配器可安装已验证工具并管理下载缓存，但不得复制组件命令或将失败转为警告。

## Stable diagnostic codes

`INVALID_USAGE`、`TOOL_MISSING`、`TOOL_VERSION_UNSUPPORTED`、`INVALID_CONFIG`、`INVALID_MODE`、`PROD_APPROVAL_REQUIRED`、`SF02_NOT_READY`、`COMPONENT_NOT_INITIALIZED`、`NO_TESTS_EXECUTED`、`STEP_FAILED`、`CONTRACT_DRIFT`、`MIGRATION_INVALID`、`SECRET_DETECTED`。

消息仅包含变量名、组件 ID 与仓库相对路径。归类为 secret、personal 或 financial 的值必须在序列化前脱敏。

## Accessibility

- 纯文本状态与最终结果始终存在。
- 颜色与图标可选，且不能承载唯一含义。
- `NO_COLOR` 与非 TTY 输出禁用颜色。
- JSON Lines 输出遵循 [`workflow-event.schema.json`](./workflow-event.schema.json)。

## Compatibility

添加支持目标为向后兼容。重命名/移除公共目标、更改其副作用类别、允许先前拒绝的环境提权，或更改成功语义为破坏性变更，需要新契约版本加迁移通知。
