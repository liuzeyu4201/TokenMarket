# Phase 0 Research

## Decision 1：余额只读账本

Billing `project_overview` 从 reservation+entries 重建。API BudgetService 经 `LedgerView` 端口读取，不直接改分录。

## Decision 2：硬预算是额外上限

`admit` 在锁内比较 `used+amount` 与 `min(hard, ledger.available+amount 窗口)`。未决占用额度，不算免费。

## Decision 3：原生示例

openai：`Authorization: Bearer` + `/openai/v1/chat/completions`。  
anthropic：`x-api-key` + `anthropic-version` + `/anthropic/v1/messages`。  
vertex：Bearer + `:generateContent`。禁止统一 chat 转换。
