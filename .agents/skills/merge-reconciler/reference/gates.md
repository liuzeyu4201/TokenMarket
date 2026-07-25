# 真门禁与验证命令（防假绿）

> 核心教训：**测试框架不做类型检查**——vitest / jest 全绿不代表代码能编译。
> 合并/恢复后必须过下列"真门禁"，否则丢失/回归会以"假绿"蒙混过关。

## 前端类型门禁

```bash
cd frontend && npx vue-tsc --noEmit
```
唯一能抓出"丢了 prop / 类型 / 组件引用"的前端门禁。`vitest run` 不替代它。

## 后端类型 / 构建门禁

```bash
cd backend
npx prisma generate                       # 先生成！否则 stale client 掩盖 schema 丢失
npx tsc --noEmit -p tsconfig.json         # 或 nest build
```

**为什么先 `prisma generate`**：prisma client 生成到 gitignored 目录。若 schema 集群被合并丢了，但本地还留着旧 client，`tsc`/`nest build` 会**假绿**。先 `generate` 让 client 跟上当前 schema，才能暴露真实丢失。

## 迁移漂移（最隐蔽的运行时崩溃）

```bash
cd backend
npx prisma migrate status                 # 看有无 "not yet applied"
npx prisma migrate deploy                 # 按需：前向应用已提交迁移（非破坏性）
```
合并常把迁移**文件**带过来、但没应用到库。症状：后端**构建过、但启动即崩**（`onApplicationBootstrap` 里查到缺列，如 `column plugins.deleted_at does not exist`，P2022），进程不监听端口 → 前端表现为 **"Network Error"**（axios 拿不到响应，非 404）。

本会话实例：merge 带来 3 个未应用迁移（email_login / plugin_pk_softdelete / add_api_key_header），`migrate deploy` 后端才起得来。

## 全量构建（monorepo）

```bash
pnpm -r --filter '@claw-company/*' build
```

## 运行时验证（构建过 ≠ 跑得起来）

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN          # 确认后端真在监听 3000
curl -s -m5 -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/<某端点>
```
HTTP 000 = 连接被拒（没监听）；正常业务码（200/400/401）= 在跑。区分"网络层不通"与"业务响应"。

## 桌面端进程（如涉及 Tauri 客户端）

```bash
pgrep -af "tauri dev|ai-staff"            # 实际二进制名见 tauri.conf.json mainBinaryName
```
注意 Makefile 里 pkill/pgrep 的进程名要与 `mainBinaryName` 一致，否则 `make desktop-stop` 杀不掉（本会话踩过：Makefile 用 claw-desktop、实际是 ai-staff）。

## 假绿清单（别被骗）

| 现象 | 真相 |
|---|---|
| `vitest run` / `jest` 全绿 | 不做类型检查，丢 prop/类型照样绿 |
| `nest build` 过 | 若 prisma client stale，schema 丢失被掩盖 → 先 `prisma generate` |
| 后端构建过 | 不等于能启动；迁移漂移会让它启动即崩 |
| 前端能打开页面 | 后端可能没起；"Network Error" 常是后端崩了不监听 |
