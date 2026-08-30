# Quickstart：Provider Binding

## 验证

```bash
cd services/api-service && make test
cd frontend && npm test -- --run src/pages/ProjectDetail.test.tsx
```

## 关键场景

1. 同一 Project 发布 openai/anthropic/vertex 三个 Binding → 均为 active，SDK 提示无 secret。
2. 两并发 publish 同协议 → 仅一个 active。
3. shared Project 发布 dedicated → 409 `MODE_MISMATCH`。
4. openai Binding 用 anthropic provider 准入 → 拒绝。
5. 专享 Connection 失效 → degraded，admit 失败且无 shared 候选。
6. 发布后启用协议成功；未发布仍 `PROVIDER_BINDING_REQUIRED`。
