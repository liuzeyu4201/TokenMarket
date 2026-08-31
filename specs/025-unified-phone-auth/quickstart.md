# Quickstart：025 统一手机号验证

```bash
uv run --project services/api-service pytest \
  services/api-service/tests/unit/test_unified_phone_auth_gates.py \
  services/api-service/tests/integration/test_unified_phone_auth.py -q
cd frontend && npx vitest run src/pages/Login.test.tsx src/pages/Register.test.tsx
```

未知号码：challenge 202 → OTP → `PROFILE_COMPLETION_REQUIRED` → 提交昵称角色 → 会话。
无 OTP 的 POST /register 必须 403。
