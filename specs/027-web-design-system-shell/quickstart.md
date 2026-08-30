# Quickstart：027 Web 设计系统

```bash
cd frontend && npx vitest run \
  src/ui src/pages/Home.test.tsx src/pages/DesignSystem.test.tsx \
  src/layouts/AppShell.test.tsx src/styles/globals.accessibility.test.ts
```

首页须同时出现三协议、共享/专享、测试额度。组件目录 `/design-system` 列出按钮/表单/表格/弹窗/通知状态。360/768/1440 规则写在 `globals.css`。
