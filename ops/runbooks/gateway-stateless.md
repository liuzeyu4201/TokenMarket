# 运行手册：Gateway 无状态快照与摘流

## 摘流

滚动发布或节点退出前调用进程终止信号。readiness 应变为 not ready（`NOT_READY`），liveness 保持 alive。新代理请求应 503。在途请求有界结束后进程退出。

## 本地用量文件

`PROXY_USAGE_WAL_DIR` 只是可丢弃缓存。删除该目录后仍必须能启动。不得把 WAL 成功当作入账成功。

## 快照

启动日志包含 `snapshot_id` 与 `catalog_major`。切换失败应保留旧快照；启动加载失败则退出。
