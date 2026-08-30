# Quickstart：买家 Project 生命周期

## 前置

- PostgreSQL 经 `make dev` 或测试夹具迁移至 `0011_buyer_projects`
- 买家工作区已登录会话（SF09）

## 验证命令

```bash
# 领域 + HTTP + 迁移
cd services/api-service && make test

# 前端
cd frontend && npm test -- --run src/pages/Projects.test.tsx src/pages/ProjectDetail.test.tsx
```

## 关键场景

1. `POST /api/v1/projects` 带 `mode=shared|dedicated` 与至少一个协议 → 201，status=draft，mode 回显。
2. `PATCH` 含 `mode` → `MODE_IMMUTABLE`，库中 mode 不变。
3. 同账号忽略大小写重名 → 409。
4. 无 Binding 时 `.../protocols/anthropic/enable` → 409 `PROVIDER_BINDING_REQUIRED`。
5. 插入 blocker 后 `DELETE` → 409，`data.blockers[].kind` 存在。
6. 归档后 `GET .../admission` 在 1 秒内 `allows_new_proxy=false`。
7. 他账号 GET 与随机 UUID 的 status/code/message 一致。
8. 卖家工作区 POST → 403。
9. UI `/projects`：模式后果文案、标签、创建入口仅买家工作区。
