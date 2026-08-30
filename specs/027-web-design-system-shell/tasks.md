# Tasks: Web 设计系统与统一应用壳

**Tests**: 先测试后实现。

## Phase 1: Setup

- [x] T001 物化 `shared/contracts/web-design-system/v1/` 并更新 `shared/contracts/README.md` 与 `tests/workflow/test_contracts.py`

## Phase 2: Foundational

- [x] T002 扩展 `frontend/src/styles/globals.css` 排版/间距/视口 token，并更新对比度测试
- [x] T003 先写 `frontend/src/ui/*.test.tsx`：Button/FormField/Notice/Dialog/Table/PageState/ErrorBoundary 状态与键盘

## Phase 3: US1 公开站

- [x] T004 [US1] 先写 Home 测试：三协议、共享/专享、测试额度、不可用入口不提交
- [x] T005 [US1] 更新 `frontend/src/pages/Home.tsx`

## Phase 4: US2 应用壳

- [x] T006 [US2] 先写 AppShell 测试：跳过链接、面包屑、工作区标识、离线提示、账户安全
- [x] T007 [US2] 实现壳层与 `ErrorBoundary` 包裹主内容 `frontend/src/layouts/AppShell.tsx`

## Phase 5: US3 组件目录

- [x] T008 [US3] 组件目录页 `/design-system` 与测试；Login/Dashboard 改用共享 Button/FormField/Notice

## Phase 6: US4 可访问

- [x] T009 [US4] 页面 a11y 扫描测试（地标、名称、dialog）；360/768/1440 CSS 断言

## Phase 7: Polish

- [x] T010 回归 Login/Register/AppShell 既有测试；evidence
