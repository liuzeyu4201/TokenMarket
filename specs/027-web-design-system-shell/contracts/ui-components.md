# UI 组件状态契约（SF08）

核心组件必须提供下列可视/可测状态，业务页不得另写一套同等交互。

| 组件 | 必选状态 |
|------|----------|
| Button | default, focus, disabled, loading |
| FormField | default, focus, error, disabled |
| Notice | info, error, success, loading |
| Dialog | open (aria-modal), closed, focus trap, restore |
| Table | caption, header, empty |
| PageState | loading, empty, error, forbidden, rate_limited, offline |
| ErrorBoundary | caught error + recover |
| Breadcrumbs | current page aria-current |
| UnavailableAction | disabled, 即将开放 |
