# Data Model

- CapacitySlot: `dimension:id` → 非负计数，上限 limit。
- DedicatedOccupancy: connection_id → project_id 唯一。
- KeyEpoch: key_id → uint64 单调；请求携带 knownEpoch，小于存储则拒绝。
