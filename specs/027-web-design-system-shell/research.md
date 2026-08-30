# Phase 0 Research：Web 设计系统

## Decision 1：共享 `frontend/src/ui` 组件，不引入新 UI 库

**Decision**: 在现有 CSS token 上增加排版/间距 token，抽出 Button、FormField、Notice、Dialog、Table、ErrorBoundary、Breadcrumbs、PageState。Login/工作台复用它们。

**Rationale**: 仓库已有 WCAG token 与表单样式；新依赖会改 npm 锁且增加体积。

**Alternatives**: 引入第三方组件库 — 超出本 SF 且需锁文件升级评审。

## Decision 2：可访问性扫描用本地规则 + Testing Library，不强制新 axe 依赖

**Decision**: 组件与页面测试断言：语义地标、可访问名称、键盘焦点、dialog aria-modal、对比度 token。serious/critical 映射为缺失名称、缺失标签、不可达弹窗、对比度不足。

**Rationale**: 新增 axe-core 会改 `package-lock.json`；本 SF 可用现有测试栈把门禁落地。SF34 再补实机 axe/浏览器矩阵。

## Decision 3：公开站静态文案，业务入口 `unavailable`

**Decision**: Home 写死产品边界。Project/连接/报价等入口使用共享 UnavailableAction（disabled + 即将开放），不 fetch。

**Rationale**: FR-009/FR-010。
