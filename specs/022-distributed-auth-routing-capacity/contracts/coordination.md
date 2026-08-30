# 协调契约

- TryDedicated(connection_id, project_id) → 至多一个 project 持有某 connection。
- TryCapacity(dimension, id, limit) 成功次数 ≤ limit。
- AllowKey(key_id, epoch) 在存储错误时失败关闭。
- Redis/内存热状态不是 Binding 或账本事实源。
