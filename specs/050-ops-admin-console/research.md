# Phase 0 Research

## Decision 1：虚拟分页目录

连接等对象用 cursor+limit 切片，total 可为 100000，响应只含当前页。

## Decision 2：配置不可原地改

active 版本只经 publish/rollback 替换。patch_active 恒拒绝。

## Decision 3：向导状态机

pending → confirmed | cancelled | expired。仅 confirmed 调用 AdminService.execute。
