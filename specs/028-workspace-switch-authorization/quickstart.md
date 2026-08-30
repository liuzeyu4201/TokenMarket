# Quickstart：028 工作区切换

```bash
uv run --project services/api-service pytest \
  services/api-service/tests/unit/test_workspace_authorization.py \
  services/api-service/tests/integration/test_workspace_switch.py \
  services/api-service/tests/unit/test_route_exclude_self.py -q
cd frontend && npx vitest run src/layouts/AppShell.test.tsx src/auth/workspace.test.ts
```

both 用户 CSRF 切换 seller 后 evaluate 买家动作应为 403。buyer 切换 seller 为 403。
