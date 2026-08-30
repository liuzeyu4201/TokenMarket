# Phase 0 Research：Anthropic 稳定数据面

## Decision 1：目录生成表

与 SF19 相同：`LoadEmbedded` 过滤 anthropic+stable。

## Decision 2：SSE 不解析事件名

内核继续按块转发；测试断言夹具字节序。

## Decision 3：anthropic-version 不进 hop-by-hop 剥离表

已不在 inboundDenied 中；合同测试锁定转发。
