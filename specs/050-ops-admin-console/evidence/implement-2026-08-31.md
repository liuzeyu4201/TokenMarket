# Evidence 050

`pytest tests/unit/test_ops_catalog.py tests/unit/test_ops_http.py tests/unit/test_admin_rbac.py tests/unit/test_admin_http.py tests/test_health.py` 28 passed.

Combined admin-service coverage 88%（ops.py 84%，catalog 95%，pipeline 92%，wizard 94%，rbac 92%）。

- 10 万连接虚拟目录：首页 50 条 + next cursor；`limit=100000` 仍钳制 ≤100。
- 导出/详情无 `sk-` / `api_key` / plaintext。
- 过期探测健康为 `unknown` + `stale`，不是 live/healthy。
- `PATCH /admin/v1/config/active` → `PATCH_ACTIVE_DENIED`；仿真失败不改 active。
- 向导取消/超时无 `result=ok` 审计；成功确认写入 request ID。
- SQL 编辑器、设余额、删审计均拒绝。
- 账务只读无法发布价格。
- 前端 `npx vitest run src/admin` 4 passed；`/admin` 不复用买家 AuthContext。
- Vite 将 `/admin/v1` 代理到 `127.0.0.1:8002`。
