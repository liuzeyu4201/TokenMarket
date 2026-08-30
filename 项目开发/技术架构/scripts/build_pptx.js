#!/usr/bin/env node
/**
 * TokenMarket 2-hour technical architecture deck.
 * Visual tokens match the product UI primary (#0B57D0) on a dark canvas.
 */
const pptxgen = require("pptxgenjs");
const path = require("path");

const OUT = path.resolve(__dirname, "../TokenMarket_技术架构.pptx");

const SW = 13.333;
const SH = 7.5;
const BG = "0A0F1A";
const SURFACE = "121A28";
const FG = "F4F6F8";
const MUTED = "9AA3B2";
const ACCENT = "0B57D0";
const GOLD = "D4B483";
const BORDER = "243044";
const DANGER = "E8A0A0";
const FONT = "Calibri";
const MONO = "Consolas";

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE16", width: SW, height: SH });
pres.layout = "WIDE16";
pres.title = "TokenMarket 技术架构分享";
pres.author = "TokenMarket Engineering";
pres.subject = "V0.1 全模块工作原理 · 约 2 小时";

function footer(slide, n, total) {
  slide.addText("TokenMarket  ·  技术架构", {
    x: 0.5, y: 7.12, w: 8, h: 0.22,
    fontFace: MONO, fontSize: 10, color: MUTED, margin: 0,
  });
  slide.addText(String(n).padStart(2, "0") + "  /  " + String(total).padStart(2, "0"), {
    x: 10.6, y: 7.12, w: 2.2, h: 0.22,
    fontFace: MONO, fontSize: 10, color: GOLD, align: "right", margin: 0,
  });
}

function kicker(slide, text) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 0.32, w: 0.18, h: 0.18, fill: { color: ACCENT },
  });
  slide.addText(text, {
    x: 0.78, y: 0.26, w: 8, h: 0.3,
    fontFace: MONO, fontSize: 11, color: GOLD, margin: 0,
  });
}

function title(slide, text, y = 0.52, h = 0.7) {
  slide.addText(text, {
    x: 0.5, y, w: 12.3, h,
    fontFace: FONT, fontSize: 28, bold: true, color: FG, margin: 0,
  });
}

function notes(slide, text) {
  slide.addNotes(text);
}

function card(slide, x, y, w, h, head, body, opt = {}) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opt.fill || SURFACE },
    line: { color: BORDER, width: 1 },
  });
  slide.addText(head, {
    x: x + 0.18, y: y + 0.12, w: w - 0.36, h: 0.32,
    fontFace: FONT, fontSize: 14, bold: true, color: opt.headColor || FG, margin: 0,
  });
  if (body) {
    slide.addText(body, {
      x: x + 0.18, y: y + 0.44, w: w - 0.36, h: h - 0.58,
      fontFace: FONT, fontSize: 13, color: MUTED, margin: 0, valign: "top",
    });
  }
}

const TOTAL = 61;
let i = 0;
function add() {
  i += 1;
  const slide = pres.addSlide();
  slide.background = { color: BG };
  footer(slide, i, TOTAL);
  return slide;
}

// ------------------------------------------------------------------ 01
{
  const s = add();
  s.addText("TECHNICAL BRIEF  ·  2 HOURS", {
    x: 0.5, y: 1.9, w: 12, h: 0.32, fontFace: MONO, fontSize: 12, color: GOLD, margin: 0,
  });
  s.addText("TokenMarket 技术架构分享", {
    x: 0.5, y: 2.3, w: 12.3, h: 0.9, fontFace: FONT, fontSize: 36, bold: true, color: FG, margin: 0,
  });
  s.addText("契约优先 monorepo  ·  全模块工作原理  ·  现状与目标分开讲", {
    x: 0.5, y: 3.3, w: 12, h: 0.4, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  s.addText("Go 网关  ·  Python 领域服务  ·  React 壳层  ·  shared/contracts  ·  infra/ops", {
    x: 0.5, y: 5.9, w: 12, h: 0.3, fontFace: MONO, fontSize: 12, color: MUTED, margin: 0,
  });
  notes(s, "2 分钟。开场：这不是融资路演，是工程师向工程师讲 V0.1 现码。强调「现状 vs 目标」贯穿全场。");
}

// 02
{
  const s = add();
  kicker(s, "怎么听");
  title(s, "先把两张图拆开");
  card(s, 0.5, 1.5, 6.0, 4.7, "V0.1 现状（今天能跑）",
    "火山 Chat Completions 一条代理路径\n注册 / 登录 / Cookie 会话\n卖家 Key 加密接入 + 买家 tmk-\n进程内 RR 选路 + 用量观察\nPG / Redis / Grafana 本地中间件");
  card(s, 6.8, 1.5, 6.0, 4.7, "目标（不要画进部署图）",
    "Kafka 计量、MinIO、Escrow、TMP\n扣费 / 账单 / 提现\n加权路由、多平台、Embeddings\n/seller /buyer /admin 业务页\n智能调度与跨实例原子游标",
    { headColor: DANGER });
  notes(s, "3 分钟。这是全场最重要的纪律。任何同学问「计费怎么算」，回答：V0.1 只记 usage，billing 是健康骨架。");
}

// 03
{
  const s = add();
  kicker(s, "AGENDA  ·  120 MIN");
  title(s, "时间盒");
  const rows = [
    ["00–15", "全景、所有权、SF 地图"],
    ["15–30", "契约、Make、ADR、健康探针"],
    ["30–55", "身份：注册、OTP、Cookie、授权"],
    ["55–80", "卖家 Key 与买家代理 Key"],
    ["80–110", "网关主链路工作原理（核心）"],
    ["110–120", "观测、交付、张力、Q&A"],
  ];
  rows.forEach((r, idx) => {
    const y = 1.45 + idx * 0.8;
    s.addText(r[0], { x: 0.5, y, w: 2.2, h: 0.55, fontFace: MONO, fontSize: 16, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 2.8, y, w: 9.5, h: 0.55, fontFace: FONT, fontSize: 18, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "1 分钟。核心 30 分钟留给网关 handleProxy。超时就砍 Billing/Admin 骨架页。");
}

// 04
{
  const s = add();
  kicker(s, "THESIS");
  title(s, "一句话");
  s.addText("网关是火山 Chat Completions 的单进程适配器。\n用户表和密文在 api-service。\n网关不得拥有用户表。", {
    x: 0.5, y: 1.8, w: 12.3, h: 2.4, fontFace: FONT, fontSize: 26, color: FG, margin: 0,
  });
  s.addText("Bearer HMAC → 选别人的卖家 Key → 允许列表过滤 → 一次上游调用 → OpenAI JSON/SSE → 一条用量观察", {
    x: 0.5, y: 4.6, w: 12.3, h: 1.2, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  notes(s, "2 分钟。让听众能用一句话复述。后面所有模块都挂在这句上。");
}

// 05
{
  const s = add();
  kicker(s, "PRECEDENCE");
  title(s, "文档冲突时怎么判");
  [
    ["1", "宪章 constitution.md", "安全、边界、测试、交付"],
    ["2", "已接受 ADR", "001 CI 薄适配 · 002 本地 Compose · 003 分层部署"],
    ["3", "现行 shared/contracts", "机器可读，先于消费者"],
    ["4", "V0.1 子 Spec / 路线图", "本期做与不做"],
    ["5", "尚未落地的架构规范段落", "不得削弱上面四条"],
  ].forEach((r, idx) => {
    const y = 1.4 + idx * 0.95;
    s.addText(r[0], { x: 0.5, y, w: 0.7, h: 0.7, fontFace: FONT, fontSize: 22, bold: true, color: GOLD, margin: 0 });
    s.addText(r[1], { x: 1.4, y, w: 6.5, h: 0.35, fontFace: FONT, fontSize: 18, bold: true, color: FG, margin: 0 });
    s.addText(r[2], { x: 1.4, y: y + 0.35, w: 10.5, h: 0.35, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0 });
  });
  notes(s, "2 分钟。举例：周度 Spec 曾写明文存 Key，宪章禁止，V0.1 采用认证加密。");
}

// 06
{
  const s = add();
  kicker(s, "CONSTITUTION");
  title(s, "宪章里跟今天最相关的四条");
  card(s, 0.5, 1.45, 6.05, 2.3, "I  边界", "网关只做认证、限流、选路、转发、计量观察、健康。领域在 Python。展示在 React。");
  card(s, 6.75, 1.45, 6.05, 2.3, "II  默认安全", "密钥不得进仓库、日志、错误、夹具。卖家 Key 认证加密。代理 Key 只存 hash。");
  card(s, 0.5, 3.95, 6.05, 2.3, "III  数据正确", "PG 是事实源。Redis 可重建。启动不自动迁移。usage 缺失不得填 0。");
  card(s, 6.75, 3.95, 6.05, 2.3, "VII  可复现交付", "根 Makefile 唯一公共入口。mode= 显式。CI 只调 make ci。");
  notes(s, "3 分钟。不念完整宪章。这四条足够约束后面每个模块的设计选择。");
}

// 07
{
  const s = add();
  kicker(s, "MONOREPO");
  title(s, "仓库地图");
  const cells = [
    ["services/proxy-gateway", "Go 公开代理 + 内部验证"],
    ["services/api-service", "用户 / 会话 / Key / 用量"],
    ["services/billing-service", "就绪骨架，不扣费"],
    ["services/admin-service", "健康骨架，无迁移"],
    ["frontend", "注册登录 + 工作台占位"],
    ["shared/contracts", "版本化 HTTP / 工作流契约"],
    ["infra", "Compose · Grafana 资产"],
    ["ops", "runbook · 告警 · 迁移所有权"],
  ];
  cells.forEach((c, idx) => {
    const col = idx % 4;
    const row = Math.floor(idx / 4);
    card(s, 0.5 + col * 3.15, 1.5 + row * 2.5, 3.0, 2.25, c[0], c[1]);
  });
  notes(s, "3 分钟。点名每个目录的一句话职责。specs/ 是 Spec Kit 功能目录，与分支名 NNN- 对齐。");
}

// 08
{
  const s = add();
  kicker(s, "RUNTIME");
  title(s, "make start 拉起什么");
  const procs = [
    ["frontend", ":5173", "注册 / 登录 / 工作台"],
    ["api-service", ":8000", "领域事实源 · 迁移顺序 1"],
    ["proxy-gateway", ":8080", "公开代理 · 内部 validate"],
    ["billing-service", ":8001", "PG ready 骨架 · 顺序 2"],
    ["admin-service", ":8002", "live/ready 恒 200"],
    ["PostgreSQL", ":5432", "事务事实源"],
    ["Redis", ":6379", "限流 / 可重建状态"],
    ["Grafana", ":3000", "V0.1 代理总览看板"],
  ];
  procs.forEach((p, idx) => {
    const y = 1.4 + idx * 0.65;
    s.addText(p[0], { x: 0.5, y, w: 3.6, h: 0.5, fontFace: MONO, fontSize: 15, color: FG, margin: 0, valign: "middle" });
    s.addText(p[1], { x: 4.2, y, w: 1.8, h: 0.5, fontFace: MONO, fontSize: 15, color: GOLD, margin: 0, valign: "middle" });
    s.addText(p[2], { x: 6.2, y, w: 6.5, h: 0.5, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0, valign: "middle" });
  });
  notes(s, "3 分钟。强调：业务服务是主机进程，永不进 compose.local.yml。Kafka 不在 SF02。");
}

// 09
{
  const s = add();
  kicker(s, "TWO PATHS");
  title(s, "两条请求路径");
  card(s, 0.5, 1.45, 6.05, 4.8, "浏览器",
    "HTTPS Vite :5173\n/api/v1 → api-service\nCookie 会话 + CSRF\n注册不发会话\n无卖家/买家 Key UI");
  card(s, 6.75, 1.45, 6.05, 4.8, "OpenAI 兼容客户端",
    "Bearer tmk-\nPOST /v1/proxy/volcano/chat/completions\n网关认证 → 选路 → 上游\n成功保持 OpenAI 形状\n前置失败走统一包络");
  notes(s, "3 分钟。画板上画这两条。后续模块都挂在其中一条。");
}

// 10
{
  const s = add();
  kicker(s, "OWNERSHIP");
  title(s, "谁拥有什么");
  s.addTable(
    [
      [
        { text: "对象", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
        { text: "所有者", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
        { text: "禁令", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
      ],
      ["users / 会话 / 授权", "api-service", "网关不得持有用户表"],
      ["卖家 Key 密文", "api-service（进程密钥环）", "不得明文落盘、进日志"],
      ["代理 Key 明文", "只在创建响应出现一次", "库内仅 secret_hash"],
      ["公开 Chat 转发", "proxy-gateway", "api-service 不打上游 Chat"],
      ["用量事实", "api-service usage_logs", "billing 不扣费"],
      ["迁移顺序", "API → Billing", "启动不自动 migrate"],
    ],
    {
      x: 0.5, y: 1.4, w: 12.3, h: 5.3,
      colW: [3.6, 4.4, 4.3],
      border: [{ pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }],
      color: FG,
      fontFace: FONT,
      fontSize: 13,
      valign: "middle",
      fill: { color: SURFACE },
    }
  );
  notes(s, "3 分钟。所有权是后面每个「为什么这样拆」的答案。");
}

// 11
{
  const s = add();
  kicker(s, "SF01–SF19");
  title(s, "功能全图");
  const groups = [
    ["工程", "01 工作流   02 本地依赖   18 日志"],
    ["身份", "03 注册   04 会话   05 授权隔离"],
    ["凭证", "06 火山验证   07 OpenAI 兼容   08–09 卖家 Key"],
    ["代理", "10 代理 Key   11 认证   12/15 非流·流   13–14 池与容量"],
    ["运营", "16 健康检查   17 用量记录   19 指标看板"],
  ];
  groups.forEach((g, idx) => {
    const y = 1.45 + idx * 0.95;
    s.addText(g[0], { x: 0.5, y, w: 1.8, h: 0.7, fontFace: FONT, fontSize: 16, bold: true, color: GOLD, margin: 0, valign: "middle" });
    s.addText(g[1], { x: 2.5, y, w: 10.3, h: 0.7, fontFace: FONT, fontSize: 16, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "3 分钟。快速过编号。告诉听众：代码比部分 spec 状态栏新，以仓库为准。");
}

// 12
{
  const s = add();
  kicker(s, "SCOPE");
  title(s, "V0.1 明确不做");
  ["多平台 / Embeddings / tools / response_format",
    "Kafka 强制计量、MinIO 对象存储",
    "扣费、账单、Escrow、TMP 积分",
    "加权路由、会话亲和、跨实例原子 RR",
    "买家/卖家/管理业务前端",
    "JWT / OAuth / 密码登录"].forEach((t, idx) => {
    s.addText("—   " + t, {
      x: 0.6, y: 1.5 + idx * 0.75, w: 12, h: 0.6,
      fontFace: FONT, fontSize: 18, color: FG, margin: 0,
    });
  });
  notes(s, "2 分钟。念完这一页，后面有人把目标功能问进来，指回这里。");
}

// 13
{
  const s = add();
  kicker(s, "MAKE");
  title(s, "唯一公共入口");
  [
    ["start / stop", "中间件 + 五个主机进程"],
    ["dev / dev-down", "只 PG / Redis / Grafana"],
    ["deploy*", "必须 mode=test|prod；Phase 1 关闸"],
    ["migrate", "API → Billing；不自动"],
    ["ci", "与 GitHub Actions 同一条链"],
    ["bootstrap", "只准备已提交锁，不改锁"],
  ].forEach((r, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    card(s, 0.5 + col * 6.4, 1.45 + row * 1.7, 6.15, 1.5, r[0], r[1]);
  });
  notes(s, "3 分钟。mode 从不从分支名推断。演示 make help 即可。");
}

// 14
{
  const s = add();
  kicker(s, "CONTRACTS");
  title(s, "先契约，后消费者");
  [
    "repository-workflow v1/v2  ·  Make 与事件信封",
    "local-environment  ·  SF02 三依赖",
    "deploy-environment  ·  分层 Compose",
    "user-registration / phone-auth-session / role-access-isolation",
    "volcano-key-validation  ·  quota 禁填 0",
    "volcano-openai-compat  ·  允许列表 / SSE / usage",
  ].forEach((t, idx) => {
    s.addText((idx + 1).toString().padStart(2, "0") + "    " + t, {
      x: 0.55, y: 1.45 + idx * 0.8, w: 12.2, h: 0.65,
      fontFace: FONT, fontSize: 16, color: FG, margin: 0, valign: "middle",
    });
  });
  notes(s, "3 分钟。008–019 多数还在 specs/ 目录，未升到 shared/contracts 总表。");
}

// 15
{
  const s = add();
  kicker(s, "HTTP SHAPE");
  title(s, "两种响应，不要混");
  card(s, 0.5, 1.5, 6.05, 4.7, "统一包络",
    "{ code, message, data,\n  request_id, timestamp }\n\n业务 API、前置失败、\n尚未开始的上游失败");
  card(s, 6.75, 1.5, 6.05, 4.7, "OpenAI 兼容",
    "成功非流：id/object/choices/usage\n成功流：text/event-stream\n已开始的 SSE 不再改包络\nusage 缺失 → omit，禁止填 0");
  notes(s, "3 分钟。这是网关最容易讲错的一点。");
}

// 16
{
  const s = add();
  kicker(s, "ADR");
  title(s, "四条已经写下的决策");
  [
    ["001", "GitHub Actions 只跑 make ci，可替换"],
    ["002", "本地依赖 Compose；Verified"],
    ["003", "分层部署；业务服务不进 compose.local"],
    ["004", "工具链 profile 显式，不靠 CI= 猜测"],
  ].forEach((r, idx) => {
    const y = 1.5 + idx * 1.2;
    s.addText("ADR " + r[0], { x: 0.5, y, w: 2.2, h: 0.9, fontFace: MONO, fontSize: 18, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 2.9, y, w: 9.8, h: 0.9, fontFace: FONT, fontSize: 20, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "2 分钟。003 实现验证仍是 Pending：make deploy 在适配器落地前 fail-closed。");
}

// 17
{
  const s = add();
  kicker(s, "HEALTH");
  title(s, "live ≠ ready");
  card(s, 0.5, 1.5, 6.05, 4.7, "/health/live",
    "进程活着即 200\n不探数据库、不探上游\n部署编排用它判断「进程还在」");
  card(s, 6.75, 1.5, 6.05, 4.7, "/health/ready",
    "仅 API / Billing 探 PostgreSQL\n一次 SELECT 1，2 秒，不重试\nGateway / Admin 不探未声明依赖\n失败体只点名 postgres");
  notes(s, "3 分钟。SF02 规定：Gateway 与 Admin 不得获得未声明依赖探针。");
}

// 18
{
  const s = add();
  kicker(s, "MIGRATE");
  title(s, "迁移所有权");
  s.addText("1   api-service\n2   billing-service\n\nadmin-service 是 non_owner\n启动路径永不 auto-migrate\nCI：隔离 PG15，前向 / 回退 / 重试 / head 恢复", {
    x: 0.5, y: 1.6, w: 12, h: 4.6, fontFace: FONT, fontSize: 22, color: FG, margin: 0,
  });
  notes(s, "2 分钟。Billing 的 0001 是空迁移。事实表都在 API。");
}

// 19
{
  const s = add();
  kicker(s, "FRONTEND");
  title(s, "壳层已经有了，业务页还没有");
  [
    ["/", "占位首页"],
    ["/register", "真 · 注册"],
    ["/login", "真 · OTP 会话"],
    ["/dashboard", "受保护占位"],
    ["无 /seller /buyer /admin", "目标架构，未实现"],
  ].forEach((r, idx) => {
    const y = 1.45 + idx * 0.95;
    s.addText(r[0], { x: 0.5, y, w: 6.5, h: 0.75, fontFace: MONO, fontSize: 18, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 7.2, y, w: 5.5, h: 0.75, fontFace: FONT, fontSize: 18, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "2 分钟。卖家 Key / 代理 Key HTTP 已在 api-service，但没有前端客户端。");
}

// 20
{
  const s = add();
  kicker(s, "SF03  ·  工作原理");
  title(s, "注册：幂等，不发会话");
  ["POST /api/v1/auth/register",
    "必须 Idempotency-Key",
    "手机规范化  ^1[3-9]\\d{9}$",
    "角色 buyer | seller | both",
    "Redis 限流失败关闭",
    "成功页写明：尚未登录"].forEach((t, idx) => {
    s.addText((idx + 1) + "   " + t, {
      x: 0.6, y: 1.45 + idx * 0.8, w: 12, h: 0.7,
      fontFace: FONT, fontSize: 20, color: FG, margin: 0,
    });
  });
  notes(s, "4 分钟。演示 curl 注册。强调不自动登录是产品与安全双重选择。");
}

// 21
{
  const s = add();
  kicker(s, "SF04  ·  工作原理");
  title(s, "202-before-dispatch");
  s.addText("先提交中性 202 和 pending 挑战，\n再由内部 dispatcher 发短信。", {
    x: 0.5, y: 1.5, w: 12.3, h: 1.4, fontFace: FONT, fontSize: 24, color: FG, margin: 0,
  });
  card(s, 0.5, 3.2, 6.05, 2.9, "防枚举", "号码是否存在，对外形状相同。不存在则 decoy 挑战（user_id=NULL），验码不成会话。");
  card(s, 6.75, 3.2, 6.05, 2.9, "生产 fail-closed", "无批准短信通道则 blocked adapter。本地/测试用 SyntheticSmsAdapter。");
  notes(s, "5 分钟。这是身份模块最关键的原理。202 不断言账号存在，也不断言送达。");
}

// 22
{
  const s = add();
  kicker(s, "SESSION");
  title(s, "不是 JWT");
  [
    ["Cookie", "__Host-tokenmarket_session"],
    ["形态", "<key-version>.<opaque-256bit>"],
    ["属性", "Secure  HttpOnly  SameSite=Lax  Path=/  无 Domain"],
    ["库存", "只存 HMAC digest，TTL 3600"],
    ["CSRF", "响应体 csrf_token，绑 session_id"],
    ["RBAC", "每次从 users 现读角色，不用 snapshot"],
  ].forEach((r, idx) => {
    const y = 1.4 + idx * 0.85;
    s.addText(r[0], { x: 0.5, y, w: 2.4, h: 0.7, fontFace: FONT, fontSize: 16, bold: true, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 3.1, y, w: 9.6, h: 0.7, fontFace: FONT, fontSize: 18, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "4 分钟。Secure cookie 决定了前端必须同源 /api 代理。");
}

// 23
{
  const s = add();
  kicker(s, "SF05");
  title(s, "角色矩阵 · 默认拒绝");
  s.addTable(
    [
      [
        { text: "动作", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
        { text: "buyer", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
        { text: "seller", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
        { text: "both", options: { fill: { color: ACCENT }, color: "FFFFFF", bold: true } },
      ],
      ["proxy_key.create / use / revoke", "allow", "deny", "allow"],
      ["seller_key.register / read / update / disable", "deny", "allow", "allow"],
      ["route_candidate_exclude_self", "allow", "deny", "allow"],
    ],
    {
      x: 0.5, y: 1.5, w: 12.3, h: 3.2,
      colW: [5.5, 2.26, 2.27, 2.27],
      color: FG, fontFace: FONT, fontSize: 14, valign: "middle",
      fill: { color: SURFACE },
      border: [{ pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }, { pt: 0.5, color: BORDER }],
    }
  );
  s.addText("请求体里的 user_id / role 必须忽略。身份只来自会话。", {
    x: 0.5, y: 5.0, w: 12.3, h: 0.8, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  notes(s, "3 分钟。both 允许同时买卖，但任何买家请求都排除自己的卖家 Key。");
}

// 24
{
  const s = add();
  kicker(s, "SELF-TRADE");
  title(s, "自买自卖：三条路径");
  card(s, 0.5, 1.45, 4.0, 4.8, "1  HTTP 矩阵", "evaluate +\nexclude-self\n写审计；失败 503");
  card(s, 4.65, 1.45, 4.0, 4.8, "2  Key HTTP 门禁", "角色粗过滤 +\n行级 seller_id\n不调 AuthorizationService");
  card(s, 8.8, 1.45, 4.0, 4.8, "3  真实代理", "Pool.Pick(buyerID)\n跳过 SellerID==BuyerID\n不调 exclude-self");
  notes(s, "5 分钟。这是授权模块最容易讲混的点。真实流量走第 3 条。resource_ownerships 与 Key 表尚未双写。");
}

// 25
{
  const s = add();
  kicker(s, "AUDIT");
  title(s, "拒绝路径 fail-closed");
  s.addText("先写审计，再返回 403 / 404。\n审计写失败 → 503，而不是静默放行。", {
    x: 0.5, y: 1.8, w: 12.3, h: 1.8, fontFace: FONT, fontSize: 24, color: FG, margin: 0,
  });
  s.addText("authorization_security_events  ·  authorization_audit_outbox", {
    x: 0.5, y: 4.2, w: 12, h: 0.5, fontFace: MONO, fontSize: 16, color: GOLD, margin: 0,
  });
  notes(s, "2 分钟。安全事件不能因为「审计库抖一下」就变成允许。");
}

// 26
{
  const s = add();
  kicker(s, "DATA");
  title(s, "身份相关表");
  [
    ["users", "phone_normalized UNIQUE · role · status · 软删"],
    ["verification_challenges", "OTP 只存 digest；decoy 的 user_id 可空"],
    ["auth_sessions", "每用户至多一条未撤销；库存 digest"],
    ["resource_ownerships", "SF05 fixtures / evaluate；未与 Key 表双写"],
    ["authentication_security_events", "认证安全事件"],
  ].forEach((r, idx) => {
    const y = 1.4 + idx * 0.95;
    s.addText(r[0], { x: 0.5, y, w: 5.3, h: 0.75, fontFace: MONO, fontSize: 16, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 6.0, y, w: 6.8, h: 0.75, fontFace: FONT, fontSize: 16, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "3 分钟。Alembic 0002–0004。0001 是空 baseline。");
}

// 27
{
  const s = add();
  kicker(s, "SF08  ·  工作原理");
  title(s, "卖家 Key 接入");
  ["角色 seller / both，必须 Idempotency-Key",
    "仅 platform=volcano",
    "调网关内部 validate（SF06，3s 硬截止）",
    "探活 GET {base}/models",
    "额度 Noop → quota_unavailable，禁止假 0",
    "quota_unavailable 可入库但 health=unknown，不可路由"].forEach((t, idx) => {
    s.addText((idx + 1) + "   " + t, {
      x: 0.55, y: 1.4 + idx * 0.8, w: 12.2, h: 0.7,
      fontFace: FONT, fontSize: 18, color: FG, margin: 0,
    });
  });
  notes(s, "5 分钟。强调：验证在网关，持久化在 API。未配置验证 URL 则 FailClosedValidator。");
}

// 28
{
  const s = add();
  kicker(s, "SF06");
  title(s, "验证：禁止假 0");
  s.addText("NoopQuotaReader\nerror_category = quota_unavailable", {
    x: 0.5, y: 1.7, w: 12.3, h: 1.6, fontFace: FONT, fontSize: 26, color: GOLD, margin: 0,
  });
  s.addText("内部接口在 test/prod 必须挂回环 listener。\n非 volcano 平台返回 HTTP 200 + unsupported_platform（不是 422）。\n静态内部 token 不足作为公网唯一防护。", {
    x: 0.5, y: 3.7, w: 12.3, h: 2.2, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "4 分钟。这是宪章「数据正确」在凭证上的落点。假 0 会让过期 Key 看起来像空闲。");
}

// 29
{
  const s = add();
  kicker(s, "CRYPTO  ·  工作原理");
  title(s, "密文怎么存");
  card(s, 0.5, 1.45, 4.0, 4.8, "算法", "SHAKE256 流加密\nHMAC-SHA256 tag\nencrypt-then-MAC");
  card(s, 4.65, 1.45, 4.0, 4.8, "分列", "nonce\nciphertext\ntag\nkey_version");
  card(s, 8.8, 1.45, 4.0, 4.8, "密钥", "只在进程环\n≥32 字节\n可读路径 re-encrypt");
  notes(s, "5 分钟。密钥材料永不与行一起持久化。指纹 HMAC 去重，对外不说「已被他人使用」。");
}

// 30
{
  const s = add();
  kicker(s, "SF09");
  title(s, "生命周期状态机");
  s.addText("active  ↔  paused  →  revoked", {
    x: 0.5, y: 1.7, w: 12.3, h: 0.8, fontFace: FONT, fontSize: 28, color: GOLD, margin: 0,
  });
  card(s, 0.5, 2.8, 4.0, 3.3, "pause", "立刻不可路由");
  card(s, 4.65, 2.8, 4.0, 3.3, "resume", "解密 · 再验证 · 额度>0 · 乐观版本");
  card(s, 8.8, 2.8, 4.0, 3.3, "revoke", "擦除密文\n再 resume → 409");
  notes(s, "4 分钟。健康状态由网关写回，不改 administrative_state。");
}

// 31
{
  const s = add();
  kicker(s, "ROUTABLE");
  title(s, "什么叫可路由");
  ["administrative_state = active",
    "health_state = healthy",
    "额度空或解析后 > 0",
    "密文仍在",
    "卖家账号 eligible（active、未删除）",
    "health=unknown 不可路由"].forEach((t, idx) => {
    s.addText("▸   " + t, {
      x: 0.6, y: 1.45 + idx * 0.8, w: 12, h: 0.7,
      fontFace: FONT, fontSize: 20, color: FG, margin: 0,
    });
  });
  notes(s, "3 分钟。Pick 用的就是这套 Routable。");
}

// 32
{
  const s = add();
  kicker(s, "INTERNAL");
  title(s, "网关怎么拿到明文 Key");
  s.addText("GET /internal/v1/seller-keys/routable\nX-Internal-Token\n响应里带解密后的 api_key", {
    x: 0.5, y: 1.7, w: 12.3, h: 2.0, fontFace: FONT, fontSize: 22, color: FG, margin: 0,
  });
  s.addText("这是信任内网 token，不是浏览器。\n网关内存持有明文；持久化仍只有密文。\n1 秒刷新一次池快照。", {
    x: 0.5, y: 4.1, w: 12.3, h: 1.8, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "3 分钟。安全模型：密文在 PG，明文只在网关进程内存与内部 TLS。");
}

// 33
{
  const s = add();
  kicker(s, "SF10  ·  工作原理");
  title(s, "买家代理 Key 只回一次");
  ["明文 tmk- + ≥128 bit hex",
    "secret_hash = HMAC-SHA256(pepper, secret)",
    "创建响应含 secret；幂等重放不再回显",
    "列表只有 masked_suffix",
    "撤销 status=revoked",
    "base_url 指向网关公开代理路径"].forEach((t, idx) => {
    s.addText((idx + 1) + "   " + t, {
      x: 0.55, y: 1.4 + idx * 0.8, w: 12.2, h: 0.7,
      fontFace: FONT, fontSize: 18, color: FG, margin: 0,
    });
  });
  notes(s, "4 分钟。网关不把明文 secret 发给 API，只发 hash。");
}

// 34
{
  const s = add();
  kicker(s, "SF11  ·  工作原理");
  title(s, "认证查找");
  s.addText("Bearer → 校验 tmk- 形态\n→ HMAC-SHA256(pepper, secret)\n→ GET /internal/v1/proxy-keys/by-hash\n→ 仅 status=active 通过", {
    x: 0.5, y: 1.5, w: 12.3, h: 2.6, fontFace: FONT, fontSize: 22, color: FG, margin: 0,
  });
  s.addText("pepper 过短 → 进程启动失败\n未知 / 撤销 / 查找失败 → 同一 401 INVALID_API_KEY", {
    x: 0.5, y: 4.4, w: 12.3, h: 1.6, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "4 分钟。防枚举：不要对撤销返回另一种 code。");
}

// 35
{
  const s = add();
  kicker(s, "CACHE TENSION");
  title(s, "正缓存 30 秒");
  s.addText("实现：命中 active 记正缓存 30s，负缓存 2s。\n规格：撤销应在 1s 内失效。", {
    x: 0.5, y: 1.8, w: 12.3, h: 1.8, fontFace: FONT, fontSize: 22, color: FG, margin: 0,
  });
  s.addText("讲架构时把它当作已知张力，而不是隐瞒。\nAdmissionLimiter：burst 32 / 16 qps / inflight 32。\n过载 → 429 AUTH_OVERLOAD。", {
    x: 0.5, y: 4.0, w: 12.3, h: 2.0, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "3 分钟。远程 LookupUnavailable 当前也映射为 401，不是 503。");
}

// 36
{
  const s = add();
  kicker(s, "GATEWAY MAP");
  title(s, "网关包，不是规范里的整棵树");
  [
    ["httpserver", "handleProxy / 包络 / 脱敏"],
    ["application", "ChatService · Validator"],
    ["chatcompat", "允许列表 · usage 完整性"],
    ["proxyauth", "HMAC · 缓存 · 闸门"],
    ["keypool", "RR · inflight · cooldown"],
    ["keyhealth", "30s 调度"],
    ["usageobs", "观察 + 可选 WAL"],
    ["volcano", "Chat 客户端 · SSE"],
  ].forEach((c, idx) => {
    const col = idx % 4;
    const row = Math.floor(idx / 4);
    card(s, 0.5 + col * 3.15, 1.45 + row * 2.55, 3.0, 2.35, c[0], c[1]);
  });
  notes(s, "3 分钟。规范里的 PipelineStage / pkg/router 加权策略不存在。实现是单 handler。");
}

// 37
{
  const s = add();
  kicker(s, "CORE  ·  30 MIN");
  title(s, "handleProxy 全链路");
  [
    "1  AuthenticateStatus",
    "2  读 body ≤ 2MiB，ParseRequestJSON",
    "3  Pool.Pick(buyerID)",
    "4  注入卖家 APIKey，生成 usage event id",
    "5  Complete 或 OpenStream（禁止重试）",
    "6  Observe → Release → 指标",
  ].forEach((t, idx) => {
    s.addText(t, {
      x: 0.6, y: 1.4 + idx * 0.8, w: 12, h: 0.7,
      fontFace: FONT, fontSize: 20, color: FG, margin: 0,
    });
  });
  notes(s, "5 分钟。这是全场核心。下面 8 页把每一步拆开。X-Request-ID ≠ usage event id。");
}

// 38
{
  const s = add();
  kicker(s, "PICK  ·  工作原理");
  title(s, "Round-Robin 怎么选");
  s.addText("for i in 0..n-1:\n    idx = (idx+1) % n\n    skip if not Routable\n    skip if SellerID == BuyerID\n    skip if cooling down\n    skip if inflight >= cap\n    inflight++ ; return", {
    x: 0.5, y: 1.4, w: 12.3, h: 4.5, fontFace: MONO, fontSize: 18, color: FG, margin: 0,
  });
  notes(s, "5 分钟。等权、先推进再取。全失败 503 NO_AVAILABLE_KEY。演示用 3 把 Key 口头走一轮。");
}

// 39
{
  const s = add();
  kicker(s, "SF14");
  title(s, "容量：官方并发的 80%");
  s.addText("cap = floor(official_concurrency × 0.8)\n未知则保守默认 32", {
    x: 0.5, y: 1.7, w: 12.3, h: 1.6, fontFace: FONT, fontSize: 26, color: GOLD, margin: 0,
  });
  s.addText("上游 429 → Cooldown 默认 30s，Retry-After 更长则用更长。\n进程内 inflight，崩溃不会跨实例释放。\nofficial_concurrency 字段常常为空。", {
    x: 0.5, y: 3.7, w: 12.3, h: 2.2, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "4 分钟。没有二次转发、没有换 Key 重放。");
}

// 40
{
  const s = add();
  kicker(s, "SF07");
  title(s, "允许列表");
  s.addText("放行    model messages stream temperature\n        max_tokens top_p stop n=1  penalty", {
    x: 0.5, y: 1.55, w: 12.3, h: 1.5, fontFace: MONO, fontSize: 18, color: FG, margin: 0,
  });
  s.addText("拒绝    tools  tool_choice  response_format\n        stream_options  user  seed  extra_body", {
    x: 0.5, y: 3.3, w: 12.3, h: 1.5, fontFace: MONO, fontSize: 18, color: DANGER, margin: 0,
  });
  s.addText("未知顶层键直接 400。content 原样 JSON。买家头不转发。", {
    x: 0.5, y: 5.1, w: 12.3, h: 0.8, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  notes(s, "3 分钟。这是兼容契约的硬边界。");
}

// 41
{
  const s = add();
  kicker(s, "USAGE RULE");
  title(s, "缺失不得填 0");
  card(s, 0.5, 1.5, 4.0, 4.7, "missing", "omit / null\n禁止 {0,0,0}");
  card(s, 4.65, 1.5, 4.0, 4.7, "inconsistent", "负数或 total < p+c\n保留原整数");
  card(s, 8.8, 1.5, 4.0, 4.7, "complete", "三分项非负\n且 total ≥ p+c\n落库 official");
  notes(s, "4 分钟。choices 可读仍算 success。假 0 会污染后续计费，所以现在就禁。");
}

// 42
{
  const s = add();
  kicker(s, "SF12");
  title(s, "非流：一次调用");
  ["FilterToProviderBody",
    "PostJSON，MaxAttempts=1",
    "NormalizeNonStream",
    "成功 200 OpenAI JSON",
    "Observe 失败可变成 503 挡住成功响应",
    "缺截止默认 60s，最大 300s"].forEach((t, idx) => {
    s.addText((idx + 1) + "   " + t, {
      x: 0.55, y: 1.4 + idx * 0.8, w: 12.2, h: 0.7,
      fontFace: FONT, fontSize: 18, color: FG, margin: 0,
    });
  });
  notes(s, "4 分钟。生成禁止自动重试，避免重复计费与重复副作用。");
}

// 43
{
  const s = add();
  kicker(s, "SF15  ·  工作原理");
  title(s, "流式边界");
  card(s, 0.5, 1.5, 6.05, 4.7, "连上游前失败", "还没写 SSE 头\n→ 统一 JSON 包络");
  card(s, 6.75, 1.5, 6.05, 4.7, "已出事件后失败", "SSE error 对象\n不发 [DONE]\ntruncated_stream");
  notes(s, "5 分钟。这是流式最关键的契约：不能在中途改成包络，也不能在截断时发 DONE。不 ReadAll 全流。写空闲默认 15s。");
}

// 44
{
  const s = add();
  kicker(s, "NO RETRY");
  title(s, "生成路径禁止换 Key 重放");
  s.addText("选中之后一次上游调用。\n失败就失败，把错误分类返回。\n不要为了可用性悄悄换一把 Key 再打一次。", {
    x: 0.5, y: 1.8, w: 12.3, h: 2.4, fontFace: FONT, fontSize: 24, color: FG, margin: 0,
  });
  s.addText("原因：客户端可能已经收到部分 SSE；重放会造成重复副作用和用量对不上。", {
    x: 0.5, y: 4.6, w: 12.3, h: 1.4, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  notes(s, "3 分钟。和「智能故障切换」目标明确相反。V0.1 选正确性。");
}

// 45
{
  const s = add();
  kicker(s, "SF16");
  title(s, "30 秒健康调度");
  [
    ["success", "healthy"],
    ["invalid / forbidden", "invalid（不会被非 healthy 改掉）"],
    ["zero quota", "expired"],
    ["429", "rate_limited，停探 30 分钟"],
    ["timeout / 5xx ×3", "down"],
  ].forEach((r, idx) => {
    const y = 1.4 + idx * 0.95;
    s.addText(r[0], { x: 0.5, y, w: 5.5, h: 0.75, fontFace: FONT, fontSize: 18, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 6.2, y, w: 6.5, h: 0.75, fontFace: FONT, fontSize: 18, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "3 分钟。不改 administrative_state。paused/revoked 不探。无多实例租约锁。");
}

// 46
{
  const s = add();
  kicker(s, "SF17");
  title(s, "用量：观察，不扣费");
  s.addText("每个请求至多一次 Observe\n落库 api-service.usage_logs\nusage_source = official | not_available\n没有 estimated", {
    x: 0.5, y: 1.6, w: 12.3, h: 2.4, fontFace: FONT, fontSize: 22, color: FG, margin: 0,
  });
  s.addText("billing-service 不参与这条路径。", {
    x: 0.5, y: 4.4, w: 12.3, h: 0.8, fontFace: FONT, fontSize: 20, color: GOLD, margin: 0,
  });
  notes(s, "3 分钟。非流 Observe 失败会挡住成功响应，与「先回客户端」规格不完全对齐。");
}

// 47
{
  const s = add();
  kicker(s, "SF18");
  title(s, "日志只留能留的");
  ["JSON · request_id 贯穿",
    "入口：method / path / 允许列表头",
    "完成：platform / stream / error_category / duration_ms / credential_ref",
    "禁止：body、Bearer、原始 Key、完整凭证"].forEach((t, idx) => {
    s.addText("▸   " + t, {
      x: 0.55, y: 1.55 + idx * 1.1, w: 12.2, h: 0.9,
      fontFace: FONT, fontSize: 20, color: FG, margin: 0,
    });
  });
  notes(s, "2 分钟。credential_ref 是 HMAC 引用，不是 Key。");
}

// 48
{
  const s = add();
  kicker(s, "SF19");
  title(s, "指标已埋，采集要单独说");
  card(s, 0.5, 1.45, 6.05, 4.8, "代码里有",
    "proxy_requests_total\nduration / auth_failures\ncapacity_rejected\nhealth_check / key_inventory\nGrafana 预配总览");
  card(s, 6.75, 1.45, 6.05, 4.8, "本地默认没有",
    "Prometheus 不在 SF02\n公开 /metrics 主要是 build_info\n业务指标在 DefaultRegisterer\n无数据不得画成 0",
    { headColor: DANGER });
  notes(s, "3 分钟。看板缺采集时必须显示 No data。");
}

// 49
{
  const s = add();
  kicker(s, "ERRORS");
  title(s, "前置失败码");
  const errs = [
    ["401", "INVALID_API_KEY"],
    ["429", "AUTH_OVERLOAD / RATE_LIMITED"],
    ["400", "INVALID_REQUEST"],
    ["503", "NO_AVAILABLE_KEY / USAGE_*"],
    ["504", "UPSTREAM_TIMEOUT"],
    ["502", "UPSTREAM_AUTH / UPSTREAM_ERROR"],
  ];
  errs.forEach((r, idx) => {
    const y = 1.4 + idx * 0.8;
    s.addText(r[0], { x: 0.5, y, w: 1.8, h: 0.65, fontFace: MONO, fontSize: 20, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 2.6, y, w: 10, h: 0.65, fontFace: MONO, fontSize: 18, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "2 分钟。流内错误是 SSE error 对象，code 如 UPSTREAM_INTERRUPTED。");
}

// 50
{
  const s = add();
  kicker(s, "BILLING");
  title(s, "计费服务是骨架");
  s.addText("/health/live  不探库\n/health/ready  SELECT 1\nAlembic 0001 是空迁移\n不扣费、不生成账单、不 Escrow", {
    x: 0.5, y: 1.7, w: 12.3, h: 2.6, fontFace: FONT, fontSize: 24, color: FG, margin: 0,
  });
  s.addText("用量事实在 api-service.usage_logs。", {
    x: 0.5, y: 4.7, w: 12.3, h: 0.8, fontFace: FONT, fontSize: 18, color: GOLD, margin: 0,
  });
  notes(s, "2 分钟。迁移顺序 2 是为以后留位，不是已经有计费域。");
}

// 51
{
  const s = add();
  kicker(s, "ADMIN");
  title(s, "管理服务是骨架");
  s.addText("只有 live / ready / metrics。\nready 恒 200。\n无迁移、无业务路由、非 SF02 探针对象。", {
    x: 0.5, y: 1.8, w: 12.3, h: 2.4, fontFace: FONT, fontSize: 24, color: FG, margin: 0,
  });
  s.addText("目标里的用户管理 / 订单仲裁 / 审核不在本期。", {
    x: 0.5, y: 4.6, w: 12.3, h: 1.0, fontFace: FONT, fontSize: 18, color: MUTED, margin: 0,
  });
  notes(s, "1 分钟。带过即可。");
}

// 52
{
  const s = add();
  kicker(s, "SF02");
  title(s, "本地中间件只有三件");
  card(s, 0.5, 1.5, 4.0, 4.7, "PostgreSQL 15.18", "命名卷保留\n事实源");
  card(s, 4.65, 1.5, 4.0, 4.7, "Redis 7.2", "限流 / 会话辅助\n可重建");
  card(s, 8.8, 1.5, 4.0, 4.7, "Grafana OSS 13.0", "普通 down 用 tmpfs\n不把 No data 画成 0");
  notes(s, "3 分钟。digest 钉死。项目名 tokenmarket-<path-hash>。禁止把业务服务写进 compose.local.yml。");
}

// 53
{
  const s = add();
  kicker(s, "ADR 003");
  title(s, "分层 Compose");
  [
    ["L", "compose.local.yml", "只中间件"],
    ["I", "compose.middleware.yml", "部署用同一三件套"],
    ["A", "compose.app.yml", "五个已构建镜像"],
    ["D", "compose.deploy.yml", "include I+A；mode=test|prod"],
  ].forEach((r, idx) => {
    const y = 1.45 + idx * 1.2;
    s.addText(r[0], { x: 0.5, y, w: 1.2, h: 0.9, fontFace: FONT, fontSize: 28, bold: true, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 1.9, y, w: 5.5, h: 0.9, fontFace: MONO, fontSize: 16, color: FG, margin: 0, valign: "middle" });
    s.addText(r[2], { x: 7.6, y, w: 5.2, h: 0.9, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0, valign: "middle" });
  });
  notes(s, "3 分钟。Phase 1 在 Docker 适配器前 fail-closed。不要恢复根级全栈 compose。");
}

// 54
{
  const s = add();
  kicker(s, "SECRETS");
  title(s, "配置与密钥");
  ["真实值只在被忽略的 .env.local",
    ".env.example 仅占位符",
    "PROXY_AUTH_PEPPER / 卖家密钥环 / INTERNAL_GATEWAY_TOKEN",
    "gitleaks · govulncheck · pip-audit · npm audit 失败关闭",
    "内部 validate listener：非 local 必须回环"].forEach((t, idx) => {
    s.addText("▸   " + t, {
      x: 0.55, y: 1.5 + idx * 0.9, w: 12.2, h: 0.75,
      fontFace: FONT, fontSize: 18, color: FG, margin: 0,
    });
  });
  notes(s, "2 分钟。");
}

// 55
{
  const s = add();
  kicker(s, "CI");
  title(s, "make ci 一条链");
  s.addText("toolchain  →  bootstrap  →  fmt-check\ntype-check  →  lint  →  test\nmigrate-check  →  migrate-integration-check\nsecurity  →  build  →  smoke  →  image-scan", {
    x: 0.5, y: 1.7, w: 12.3, h: 3.2, fontFace: MONO, fontSize: 20, color: FG, margin: 0,
  });
  s.addText("GitHub Actions 只调用这一条，不在 YAML 里重复门禁。", {
    x: 0.5, y: 5.2, w: 12.3, h: 0.7, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0,
  });
  notes(s, "2 分钟。");
}

// 56
{
  const s = add();
  kicker(s, "ALL MODULES");
  title(s, "模块清单");
  const mods = [
    "proxy-gateway  httpserver / chatcompat / proxyauth / keypool / keyhealth / usageobs / volcano",
    "api-service  users / auth / authorization / sellerkeys / proxykeys / usage",
    "billing-service  live/ready 骨架",
    "admin-service  live/ready 骨架",
    "frontend  register / login / dashboard 占位",
    "shared/contracts  8 个已升版本契约",
    "infra  compose.local/app/middleware/deploy  ·  grafana",
    "ops  runbooks / alerts / owners.json / workflow",
  ];
  mods.forEach((t, idx) => {
    s.addText(t, {
      x: 0.5, y: 1.35 + idx * 0.65, w: 12.3, h: 0.58,
      fontFace: FONT, fontSize: 14, color: FG, margin: 0, valign: "middle",
    });
  });
  notes(s, "3 分钟。用这一页确认「全面」：每个目录都点过。");
}

// 57
{
  const s = add();
  kicker(s, "TENSIONS");
  title(s, "已知张力（必须说）");
  [
    "正缓存 30s vs 撤销 1s",
    "进程内 inflight，无跨实例租约",
    "多副本 RR 不保证全局公平",
    "/metrics 刮取缺口；无 Prometheus",
    "非流用量失败会挡住成功响应",
    "ownership 表与 Key 表未双写",
    "Key HTTP 未走 AuthorizationService",
    "DB 宕时可 fallback 内存 store",
  ].forEach((t, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    s.addText("·  " + t, {
      x: 0.5 + col * 6.4, y: 1.45 + row * 1.2, w: 6.2, h: 1.0,
      fontFace: FONT, fontSize: 16, color: FG, margin: 0, valign: "middle",
    });
  });
  notes(s, "4 分钟。诚实讲张力比画一张完美目标图更有用。");
}

// 58
{
  const s = add();
  kicker(s, "READ");
  title(s, "散会后读什么");
  [
    ["现状数据流", "docs/architecture/overview.md"],
    ["目标架构", "项目开发/1-项目架构与目录结构.md"],
    ["子 Spec 索引", "项目开发/V0.1/V0.1_0712/specs/README.md"],
    ["契约", "shared/contracts/README.md"],
    ["详细 PDF", "项目开发/技术架构/TokenMarket_技术架构.pdf"],
  ].forEach((r, idx) => {
    const y = 1.45 + idx * 0.95;
    s.addText(r[0], { x: 0.5, y, w: 3.5, h: 0.75, fontFace: FONT, fontSize: 16, bold: true, color: GOLD, margin: 0, valign: "middle" });
    s.addText(r[1], { x: 4.1, y, w: 8.7, h: 0.75, fontFace: MONO, fontSize: 14, color: FG, margin: 0, valign: "middle" });
  });
  notes(s, "2 分钟。");
}

// 59
{
  const s = add();
  kicker(s, "RECAP");
  title(s, "带走三句");
  s.addText("1  网关不拥有用户表。\n2  生成禁止重试，usage 禁止填 0。\n3  目标架构不要画进今天的部署图。", {
    x: 0.5, y: 1.8, w: 12.3, h: 3.6, fontFace: FONT, fontSize: 26, color: FG, margin: 0,
  });
  notes(s, "2 分钟。");
}

// 60
{
  const s = add();
  kicker(s, "Q&A");
  title(s, "问题");
  s.addText("优先讨论现码路径。\n目标能力请标明版本。", {
    x: 0.5, y: 2.2, w: 12.3, h: 2.2, fontFace: FONT, fontSize: 28, color: FG, margin: 0,
  });
  notes(s, "剩余时间。常见问题：计费何时做、多平台何时做、为何不用 JWT、为何不用 Kafka。");
}

// 61
{
  const s = add();
  s.addText("TOKENMARKET", {
    x: 0.5, y: 2.3, w: 12.3, h: 0.4, fontFace: MONO, fontSize: 14, color: GOLD, margin: 0,
  });
  s.addText("让闲置额度流动起来。\n先把代理主链路做对。", {
    x: 0.5, y: 2.8, w: 12.3, h: 1.8, fontFace: FONT, fontSize: 28, bold: true, color: FG, margin: 0,
  });
  notes(s, "结束。指向详细 PDF。");
}

if (i !== TOTAL) {
  console.error("slide count mismatch", i, TOTAL);
  process.exit(1);
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote", OUT);
});
