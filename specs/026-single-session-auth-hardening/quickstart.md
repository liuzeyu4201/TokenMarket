# Quickstart：026 单会话加固

```bash
uv run --project services/api-service pytest \
  services/api-service/tests/unit/test_session_generation.py \
  services/api-service/tests/integration/test_session_generation.py -q
cd frontend && npx vitest run src/pages/AccountSecurity.test.tsx
```

同一账号第二次登录后，旧 cookie 引导必须 `UNAUTHENTICATED`。全部退出提升世代。安全页不含 token。
