#!/usr/bin/env bash
# merge-reconciler 公共库：自动探测合并对比轴 OURS / THEIRS / BASE / RESULT
#
# 对比轴语义：
#   OURS    当前分支合并前的状态（"ours" / 我方）
#   THEIRS  合过来的分支（"theirs" / incoming）
#   BASE    两者的 merge-base（三方合并基线）
#   RESULT  当前实际结果（合并进行中=工作区；合并已提交=HEAD）
#
# 探测优先级：
#   1) 合并进行中（存在 .git/MERGE_HEAD）→ THEIRS=MERGE_HEAD, OURS=HEAD, RESULT=:worktree
#   2) HEAD 是 merge commit（有第二父）→ OURS=HEAD^1, THEIRS=HEAD^2, RESULT=HEAD
#   3) 否则用 $1 或环境变量 INCOMING 作 THEIRS，OURS=HEAD, RESULT=HEAD
#      （都没有则报错，提示用户给出 incoming 分支名）
#
# 用法：source 本文件后即可读取导出的变量；或直接执行打印对比轴。
#   source "$(dirname "$0")/_common.sh"   # 在其它脚本里
#   bash _common.sh [incoming-ref]        # 直接看对比轴

set -euo pipefail

# 切到 git 仓库根目录，保证后续相对路径稳定
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# revert 提交主题识别（中英 + 大小写）
REVERT_RE='revert|回滚|[Rr]evert'

# 噪音目录：默认排除非源码区，避免淹没真实信号（可被调用方用 NOISE_RE 覆盖）
NOISE_RE="${NOISE_RE:-^(client/|specs/|docs/|\.specify/|\.agents/|\.codex/|\.claude/)}"

# 敏感/本地文件：绝不跨分支恢复（红线）
SENSITIVE_RE="${SENSITIVE_RE:-(^|/)dev\.db$|\.env(\.|$)}"

_mr_incoming_arg="${1:-${INCOMING:-}}"

if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
  MR_MODE="in-merge"
  OURS="HEAD"
  THEIRS="$(git rev-parse MERGE_HEAD)"
  RESULT="WORKTREE"   # 特殊值：表示工作区/index，需用 git show :0:<path> 或读盘
elif git rev-parse -q --verify 'HEAD^2' >/dev/null 2>&1; then
  MR_MODE="merge-commit"
  OURS="$(git rev-parse 'HEAD^1')"
  THEIRS="$(git rev-parse 'HEAD^2')"
  RESULT="HEAD"
elif [ -n "$_mr_incoming_arg" ]; then
  MR_MODE="explicit"
  OURS="HEAD"
  if ! THEIRS="$(git rev-parse -q --verify "$_mr_incoming_arg" 2>/dev/null)"; then
    echo "[merge-reconciler] 错误：无法解析 incoming 分支 '$_mr_incoming_arg'" >&2
    exit 2
  fi
  RESULT="HEAD"
else
  cat >&2 <<'EOF'
[merge-reconciler] 探测不到对比轴：
  - 当前不在合并进行中（无 MERGE_HEAD）
  - HEAD 也不是 merge commit（无第二父）
请提供「合过来的分支」名作为参数：
  bash _common.sh <incoming-ref>      或      INCOMING=<ref> source _common.sh
EOF
  exit 2
fi

BASE="$(git merge-base "$OURS" "$THEIRS")"

export REPO_ROOT MR_MODE OURS THEIRS BASE RESULT REVERT_RE NOISE_RE SENSITIVE_RE

# 读取某参照点下某文件内容到 stdout（RESULT=WORKTREE 时读工作区）。
# 用法：mr_show <ref-or-RESULT> <path>
mr_show() {
  local ref="$1" path="$2"
  if [ "$ref" = "WORKTREE" ]; then
    [ -f "$path" ] && cat -- "$path" || return 0
  else
    git show "$ref:$path" 2>/dev/null || return 0
  fi
}

# 判断某参照点下某文件是否存在。用法：mr_exists <ref-or-RESULT> <path>
mr_exists() {
  local ref="$1" path="$2"
  if [ "$ref" = "WORKTREE" ]; then
    [ -f "$path" ]
  else
    git cat-file -e "$ref:$path" 2>/dev/null
  fi
}

# 列出某参照点的 path→blob 映射到 stdout（"path blob" 每行，路径含空格安全）。
# RESULT=WORKTREE（合并进行中）时读 index 的 stage-0（已解决项）；未解决冲突项（stage 1/2/3）
# 由 git 显式标记、留给用户手解，不纳入 blob 比对。
mr_tree() {
  local ref="$1"
  if [ "$ref" = "WORKTREE" ]; then
    # ls-files -s 行格式：<mode> SP <sha> SP <stage> TAB <path>
    git ls-files -s | awk -F'\t' '{ n=split($1,m," "); if (m[3]=="0") print $2" "m[2] }'
    return
  fi
  # ls-tree 行格式：<mode> SP <type> SP <sha> TAB <path>；sha 为 $1 的第 3 段
  git ls-tree -r "$ref" | awk -F'\t' '{ n=split($1,m," "); print $2" "m[3] }'
}

# 直接执行时打印对比轴
if [ "${BASH_SOURCE[0]:-}" = "${0}" ]; then
  printf '模式(MR_MODE): %s\n' "$MR_MODE"
  for pair in "OURS:$OURS" "THEIRS:$THEIRS" "BASE:$BASE" "RESULT:$RESULT"; do
    name="${pair%%:*}"; ref="${pair##*:}"
    if [ "$ref" = "WORKTREE" ]; then
      printf '  %-7s %s\n' "$name" "(工作区/index)"
    else
      printf '  %-7s %s\n' "$name" "$(git log -1 --format='%h %ci %d %s' "$ref" 2>/dev/null)"
    fi
  done
fi
