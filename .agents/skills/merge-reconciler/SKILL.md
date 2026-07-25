---
name: "merge-reconciler"
description: >
  ClawCompany 专属分支合并对账师。当用户在当前分支合并了某分支、出现冲突，
  或要做 revert 静默丢失恢复、排查"合并后退回对方旧版"的行为回归时激活。
  对比轴=当前分支(ours/HEAD)↔合过来的分支(theirs，自动取 MERGE_HEAD 或 merge commit 第二父)，
  基线为 merge-base。blob 四点比对分类、commit 级安全整取、标记行为与前向点状扫描；
  用真门禁(vue-tsc/nest build/prisma)防假绿。
  红线：不随意丢弃代码（任何删除/覆盖前先发用户确认并说原因）、dev.db 与 .env.* 绝不从对方分支恢复、
  对方没有而本侧独有的文件不删、仅用户明确要求时提交/推送。
argument-hint: "可选 incoming 分支名（留空则自动探测：合并中取 MERGE_HEAD，或 merge commit 的第二父）"
metadata:
  author: "claw-company"
  primary-goal: "merge-recovery"
user-invocable: true
disable-model-invocation: false
---

## User Input

```text
$ARGUMENTS
```

`$ARGUMENTS` 可选给「合过来的分支」名。留空时由 `scripts/_common.sh` 自动探测对比轴；若既不在合并态、HEAD 也不是 merge commit，则**停下追问**：用户这次是把哪个分支合进当前分支？

---

## 激活条件

- "我合并了 X，有冲突，帮我解决" / "解决一下当前合并冲突"
- "合并后好像丢了东西" / "revert 把内容删了，恢复一下" / "这功能合并前有、现在没了"
- "排查下合并有没有把 \<某分支\> 的前向改动退回旧版" / "统一查一遍合并回归"

**反例（不激活）**：
- 单个文件的小冲突、用户自己手解即可
- 与合并无关的常规开发/改 bug
- 跨仓库迁移、非 git 的内容合并

---

## 红线（必须遵守）

### 🔴 最高优先：不随意丢弃代码

任何会**删除 / 覆盖 / 丢弃既有代码内容**的操作——`git checkout <对方> -- <file>` 覆盖本侧、删文件、graft 时覆盖、`git restore` 等——在执行前**必须给用户发消息确认**，列清三件事：

| 要素 | 说明 |
|---|---|
| 将丢弃什么 | 哪个文件、哪些行/块会被替换或删除 |
| 丢弃原因 | 为什么判断该丢（如：被 revert 误删、退回了旧版、对方是权威版） |
| 来源依据 | 用谁的版本替代、依据哪侧（OURS/THEIRS/BASE）及佐证 |

判断不确定时**一律停下问**，绝不擅自丢。区分两种情况：
- **纯补回缺失**（RESULT 当前没有该内容、从对方恢复被删的东西）→ 不算丢弃，可执行（仍在提交前汇报）。
- **覆盖既有**（RESULT 已有非空代码、会被替换/回退）→ 属丢弃，**先确认**。

### 其它红线

| 对象 | 规则 |
|---|---|
| `dev.db`、`**/.env*` | ❌ 绝不从对方分支恢复（本地库 / 敏感配置） |
| 对方没有、本侧独有的文件 | ❌ 不删（"从对方整取"会变误删；脚本已默认剔除） |
| 提交 / 推送 | ⚠️ 仅用户明确要求时；不擅自 push |
| 外向 / 不可逆操作 | 先确认 |

---

## 核心心智模型

- **git 合并的是 commit，不是内容**。三方合并对"一侧删除、另一侧未改"的文件判定为"保留删除"——于是被 revert 删掉、而对方未改的内容会**静默丢失**，且不报冲突。
- **merge-base 由提交拓扑决定，与分支名无关**。对方分支若已是 HEAD 祖先，重新 `git merge` 是 no-op（"Already up to date"），**救不回**已丢内容；恢复只能显式 `git checkout <对方> -- <file>`。
- **对比轴四参照点**（`scripts/_common.sh` 自动探测）：

| 记号 | 含义 | 探测 |
|---|---|---|
| `OURS` | 当前分支合并前状态（我方） | 合并中=`HEAD`；merge commit=`HEAD^1`；否则=`HEAD` |
| `THEIRS` | 合过来的分支（incoming） | 合并中=`MERGE_HEAD`；merge commit=`HEAD^2`；否则=用户给的 ref |
| `BASE` | 合并基线 | `git merge-base OURS THEIRS` |
| `RESULT` | 当前实际结果 | 合并中=工作区/index(stage0)；已提交=`HEAD` |

深入原理、反向陷阱、真实战例见 `reference/playbook.md`（**动手前必读**）。

---

## 第 0 步：探测对比轴

```bash
bash .Codex/skills/merge-reconciler/scripts/_common.sh [incoming-ref]
```

打印 OURS/THEIRS/BASE/RESULT 的 SHA、分支、日期。探测不到 incoming（非合并态且用户没给）→ 停下追问。确认对比轴无误再往下。

---

## §A 静默丢失恢复（revert 误删找回）

1. 跑分类器：
   ```bash
   bash .Codex/skills/merge-reconciler/scripts/classify-blobs.sh [incoming-ref]
   ```
   得 **[A] 安全整取候选**（对方版权威、RESULT 缺失或被截断）与 **[B] 回归候选**（见 §B）。脚本已默认剔除 `dev.db`/`.env`/噪音目录。

2. 对 [A] 清单逐项判断"补回缺失"还是"覆盖既有"：
   - 纯补回（RESULT 没有）→ 可整取；
   - 会覆盖 RESULT 既有非空代码 → **走红线确认闸**，列清单 + 原因发用户，确认后再取。

3. 整取（确认后）：先用 ls-tree 求交集剔除对方不存在的路径，避免 `git checkout` 整批回滚：
   ```bash
   # 仅取「对方存在」且「非本侧独有」的安全清单
   tr '\n' '\0' < safe_list.txt | xargs -0 git checkout "$THEIRS" --
   ```

4. 验证（§C）后再考虑提交（§D）。

---

## §B 回归扫描（"合并后退回对方旧版"）

三路并用，互补：

1. **blob 比对**：`classify-blobs.sh` 的 **[B]** 段 = `OURS 真前向 且 RESULT==THEIRS 且 RESULT≠OURS`。
2. **标记行为扫描**：找某侧专属行为被丢（如 desktop 隐藏标签条件）：
   ```bash
   bash .Codex/skills/merge-reconciler/scripts/scan-markers.sh [marker-regex] [OURS|THEIRS]
   ```
3. **前向点状扫描**：找某侧前向新增的具体行被丢：
   ```bash
   bash .Codex/skills/merge-reconciler/scripts/scan-lost-forward.sh [OURS|THEIRS]
   ```

**方向纪律 + 假阳甄别（关键，详见 playbook）**：
- `git diff A B`：`-` 是 A、`+` 是 B，别读反（本会话因读反差点改错）。
- **反向陷阱**：某侧"前向"若后来被自己 revert 掉（净回退），则 RESULT 经对方保留**反而正确**，不是回归。先确认该前向在对方 tip 是否幸存。
- **行/集合 diff 噪音高**：对重构/改写过的文件大量假阳。每条候选必须**语义核实**——该标识符/行为在 RESULT 是否**真的完全没有**（常只是换了写法，或 RESULT 是更新/超集）。

**修复前确认闸**：扫描只读、产出候选清单。任何会覆盖/回退 RESULT 既有代码的修复（整取某侧版、回退某行/块）→ 先发用户确认（改哪个文件 + 丢弃什么 + 为什么 + 依据哪侧）。**只补不删的点状 graft** 可径直做，但仍在提交前汇报。

---

## §C 真门禁验证（防假绿）

合并/恢复后**必须**过真门禁——测试框架不做类型检查，会假绿。详见 `reference/gates.md`，要点：

- 前端类型门禁：`cd frontend && npx vue-tsc --noEmit`
- 后端：`cd backend && npx prisma generate && npx tsc --noEmit -p tsconfig.json`（**先 generate**，stale prisma client 会掩盖 schema 丢失）
- 迁移漂移：`npx prisma migrate status` →（按需）`migrate deploy`。漂移会导致后端启动即崩、不监听端口，前端表现 "Network Error"。
- 全量构建：`pnpm -r --filter '@claw-company/*' build`
- 运行时：构建过 ≠ 跑得起来。确认进程真监听：`lsof -nP -iTCP:3000 -sTCP:LISTEN`
- 前端测试用 `vitest run`（vitest/jest 都不做类型检查）。

---

## §D 提交（仅用户要求时）

- 信息格式 `<type>(<scope>): <subject>`；scope ∈ `staff|channel|skill|tool|conversation|group|llm|spec|config|chat|desktop|prisma` 等贴切词。
- 一个修复一个 commit，message 写清"丢了什么 / 来源 / 依据"。
- **不擅自 push**；推送由用户明确发起。

---

## 工具坑（macOS / zsh / git）

- **BSD xargs**（macOS）无 `-d` / `-a`：用 `tr '\n' '\0' | xargs -0`。
- **zsh 无 `mapfile`**：用 `while read` 或数组替代。
- **逐文件 `git show` 循环慢且后台易空跑**：优先 `git ls-tree -r` 取 path→blob 做**集合运算**、blob-SHA 比对（脚本已如此）。
- **`git checkout <tree> -- <多路径>` 遇任一无效 pathspec 会整批回滚**：先 ls-tree 求交集剔除不存在路径。
- 默认过滤噪音目录（`client/ specs/ docs/ .specify/ .agents/ .codex/ .Codex/`）；可用 env `NOISE_RE` 覆盖。

---

## 自检清单（提交前）

- [ ] 所有丢弃/覆盖操作均已发用户确认（含"丢弃什么 + 原因 + 依据"）
- [ ] 未碰 `dev.db` / `.env*`；未删"对方没有、本侧独有"的文件
- [ ] §C 门禁全绿：`vue-tsc --noEmit`、后端 `tsc/nest build`（已先 `prisma generate`）、`migrate status` 干净、关键进程真监听
- [ ] §B 候选均已语义核实（区分真回归 vs 重构噪音/反向陷阱），未盲改
- [ ] 提交信息规范；未擅自 push
