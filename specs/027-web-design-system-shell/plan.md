# Implementation Plan: Web 设计系统与统一应用壳

**Branch**: `027-web-design-system-shell` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

## Summary

将现有占位前端升级为共享 token + 基础组件 + 公开站文案 + 应用壳（导航、面包屑、工作区标识、全局状态）。不实现买家/卖家业务。自动化覆盖组件状态、三视口 CSS 门禁、键盘/焦点与可访问性扫描。

## Technical Context

**Language/Version**: TypeScript 严格、React 19、Vite（`frontend/`）

**Primary Dependencies**: 既有 AppShell、Login、Home、vitest、Testing Library、globals.css token

**Storage**: N/A（无新持久化）

**Testing**: Vitest + Testing Library；对比度沿用 globals.accessibility.test.ts；组件交互测试；轻量 a11y 扫描（不新增付费服务）

**Affected Components**: `frontend/src/`、`shared/contracts/web-design-system/v1/`

## Constitution Check

### Pre-Research Gate: PASS

无密钥；契约先行（UI 状态清单）；不引入跨服务存储；中文文档。

### Post-Design Gate: PASS

无假数据伪装业务；受保护路由保持鉴权；token 对比度门禁保留。

## Project Structure

```text
shared/contracts/web-design-system/v1/
frontend/src/ui/          # 共享基础组件
frontend/src/styles/globals.css
frontend/src/layouts/AppShell.tsx
frontend/src/pages/Home.tsx
frontend/src/pages/DesignSystem.tsx
```

## Complexity Tracking

无宪章违规。不新增 UI 框架。
