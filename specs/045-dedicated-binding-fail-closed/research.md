# Phase 0 Research

## Decision 1：网关 DedicatedSelector

Select 只返回当前绑定 Connection。status≠active 或 health≠healthy → `DEDICATED_UNAVAILABLE`。共享候选不进入该 Selector。

## Decision 2：更换事务

在 Binding 行上原子写入 `connection_id=new`、`draining_connection_id=old`、`status=active`、version+1。旧 Connection lifecycle=draining，新=bound。

## Decision 3：亲和

`SelectConnection` 允许当前绑定或 draining 旧 ID；其它 ID 失败关闭，避免旧资源误送新连接。
