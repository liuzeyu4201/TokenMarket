# merge-reconciler playbook —— 机制原理 · 陷阱 · 真实战例

> 动手前读完本文。SKILL.md 是流程；本文解释"为什么"，帮你避开判断陷阱。

## 1. revert 静默丢失机制

合并是 **commit 级三方合并**，不是逐行内容合并。对每个文件，git 比较 `BASE / OURS / THEIRS` 三方：

| BASE | OURS | THEIRS | 三方结果 |
|---|---|---|---|
| 有内容 X | 删了 X（如经 revert） | 未改（仍是 X） | **保留删除** → X 丢失，且**不报冲突** |
| 有内容 X | 改成 X' | 未改 | 取 X' |
| 有 X | 未改 | 改成 X'' | 取 X'' |
| 有 X | 删 | 改成 X'' | **modify/delete 冲突**（git 会标记，反而安全） |

**致命点**：第 1 行——一侧 revert 删掉、另一侧未动的内容，被静默判为删除。git 只对"两侧都动且冲突"报警；"一侧删一侧没动"无声通过。这类丢失**看不见、测不出**（若能编译），最隐蔽。

**为什么重新合并救不回**：merge-base 由拓扑决定。若对方分支已是 HEAD 祖先，`git merge 对方` = "Already up to date"（no-op）。三方合并的 base 不变，对同样的文件仍判"保留删除"。恢复**只能显式** `git checkout <对方> -- <file>`。

## 2. 反向陷阱：某侧 revert 掉了自己的前向

最容易判错的情形。`classify-blobs.sh` 把"RESULT==THEIRS 且 OURS 前向 且 RESULT≠OURS"列为回归候选，但有一类是**假回归**：

> OURS 曾向前加了特性 F（一个非 revert 提交），**后来又被 OURS 自己 revert 回退**。于是 OURS tip 净效果是"没有 F"。而 THEIRS（对方）保留了 F。RESULT 经 THEIRS 拿到 F —— 这是**对的**，不是丢了 OURS 的前向。

**本会话实例**：`backend/src/installations/installations.service.ts`
- `dc7fef35` 在 master-dev 加了"单点登录互踢"（MAX=1，新登录踢掉其它全部）。
- 随后 master-dev 的 revert `09cc889a` 把它回退成"最多 5 台、只踢最旧 1 台"。
- desktop 侧保留了单点登录。合并结果 RESULT = 单点登录（经 desktop）。
- 我一度**把 master/HEAD 读反**，以为"master 是单点登录、HEAD 退回 5 台"，差点 `git checkout master` 把单点登录改没。

教训：判回归前，先确认 OURS 的"前向"在 **OURS tip 是否幸存**（没被自己 revert）。再确认 `git diff` 方向（见 §4）。

## 3. 真实回归战例（"问题2"：合并退回对方旧版）

这三例是**真**回归——OURS（master-dev）的前向在 tip 幸存，但合并结果退回了对方旧版：

1. **SessionList 隐藏 Desktop 标签**（修复 `461a7ae7`）
   - desktop 提交 `2a057809` 把渲染条件设为 `source !== 'web' && source !== 'desktop'`（隐藏 Desktop 标签）。
   - 070 重设计 `39baa223` 重写 SessionList.vue，条件退回 `source !== 'web'` → 标签重现。
   - blob 比对判为 OK-fwd（重设计是最新结构），但**点状丢了一行 desktop 行为** → `scan-markers.sh` 命中。
   - 修复：补回 `&& session.source !== 'desktop'`（只补一行，不丢弃 → 无需确认闸，提交前汇报）。

2. **StaffListView 进会话即建 session**（修复 `fa962bda`）
   - master-dev 改 `handleChat` 为纯跳转（懒创建，首条消息才建 session）。
   - 合并取了 desktop 旧版：进入即 `ensureSession({reuseEmpty:true})` 预建。
   - `classify-blobs.sh` 的 [B] 段命中（HEAD==desktop 且 master 前向）。
   - 修复：移除预创建，对齐 master 懒创建。

3. **ChatWindow 执行模式锁跨组件透传断链**（修复 `a5f64297`）
   - 链路 ChatView(父,已传) → ChatWindow(中间) → ChatInputBar(子,已收 UI)。
   - 070 重写 ChatWindow 时丢了中间透传（props/emit），链在中间断 → 事件丢、状态不下传。
   - 三组件比对（desktop=3处 / HEAD=0处）定位到只有中间层缺。
   - 修复：按 desktop 实现补回 4 props + 1 emit + 模板透传（只补不删）。

## 4. 假阳甄别规则（最重要的纪律）

行级 / 集合级 diff 对**被重构/改写**的文件假阳极高——同一逻辑换了变量名、加了类型标注、改了日志前缀，集合差就判"丢失"。**每条候选必须语义核实**：

- **看标识符是否真缺**：`git grep '<关键标识符>' <RESULT-ref> -- <file>` 或读 RESULT 版本。在则是噪音。
- **RESULT 常是更新/超集**：本会话点状扫描 14 个嫌疑全是假阳——`types/index.ts` HEAD 多了 `tool_route`/`desktop-local`；`services/chat.ts` HEAD `autoConnect: !!getAuthToken()` 更优；`auth.ts` 的 `$reset` 搬进了 `resetFrontendUserSession`。
- **行为可能搬了位置**：函数移到工具文件、守卫从单行变块。语义在即可。
- **方向**：`git diff A B`，`-`=A、`+`=B。要看"RESULT 缺了对方的什么"，用 `git diff RESULT 对方`，看 `+` 行（对方有 RESULT 无）。

只有"标识符/行为在 RESULT 完全找不到"才是真丢失。真丢失也要按红线判断"补回缺失（直接做）"还是"覆盖既有（先确认）"。

## 5. 本会话的分支映射（实例，非默认）

- OURS = `master-dev`（origin/master-dev / 当前主线侧）
- THEIRS = `050-desktop-client`（origin/050-desktop-client / 合过来的桌面端）
- 一次合并的 merge-base 当时 = `7e7e7053`（后续主线推进后会变）

这只是举例。skill 的对比轴永远由 `_common.sh` 按"当前分支 ↔ 合过来的分支"自动探测，不写死这两个名字。
