# Data Model：设计系统（UI 状态，非持久化）

## DesignToken

命名颜色、字号、间距、焦点环、状态色。必须能被对比度测试读取。

## PageStatus

`loading` | `empty` | `error` | `forbidden` | `rate_limited` | `offline` | `ready`

## WorkspaceIdentity（展示）

来自当前会话角色的只读标识（买家/卖家/买家与卖家）。切换动作本 SF 禁用。

## UnavailableAction

标签、原因（即将开放）、不可提交。
