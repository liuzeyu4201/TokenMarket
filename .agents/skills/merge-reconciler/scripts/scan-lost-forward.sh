#!/usr/bin/env bash
# scan-lost-forward.sh —— 前向点状扫描（只读）
#
# 找"某侧(默认 OURS)向前新增的具体行，被合并结果丢掉"的回归。
# 做法：对 该侧"非 revert 真前向"改过的共享代码文件，计算
#   (该侧相对 BASE 新增的去噪行) − (RESULT 的去噪行) = 候选丢失行。
# 噪音过滤：去首尾空白、丢空行/纯括号/import/注释/<10 字符短行。
# 注意：行级集合差对"被重构/改写"的文件假阳极高（同逻辑换了写法即判丢失）。
#       结果必排序后逐个语义核实——标识符在 RESULT 是否真完全没有；RESULT 常是更新/超集。
#
# 用法：bash scan-lost-forward.sh [side]    side=OURS(默认)|THEIRS
#       incoming ref 经 env：INCOMING=<ref> bash scan-lost-forward.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$DIR/_common.sh"

SIDE="${1:-OURS}"
case "$SIDE" in OURS) FWD_REF="$OURS" ;; THEIRS) FWD_REF="$THEIRS" ;; *) echo "side 须为 OURS 或 THEIRS" >&2; exit 2 ;; esac

echo "对比轴：前向侧=$SIDE($FWD_REF)  BASE=$BASE  RESULT=$RESULT  (模式 $MR_MODE)" >&2
echo "===================================================================="

# 该侧非 revert 真前向文件集
git log "$BASE..$FWD_REF" --name-only --pretty=format:'@@@%s' 2>/dev/null \
  | awk -v re="$REVERT_RE" '/^@@@/{rev=($0~re)?1:0;next} NF&&!rev{print}' | sort -u > /tmp/_mr_fwd.$$
trap 'rm -f /tmp/_mr_fwd.$$ /tmp/_mr_detail.$$' EXIT

NORM='s/^[[:space:]]*//;s/[[:space:]]*$//'
FILTER='^$|^[{}()[];,]+$|^(import |export \{|from |//|\*|/\*)'
: > /tmp/_mr_detail.$$
results=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    frontend/src/*|backend/src/*|packages/*/src/*) ;;
    *) continue ;;
  esac
  case "$f" in *.spec.ts|*__tests__*|*.snap) continue ;; esac
  mr_exists "$FWD_REF" "$f" || continue
  mr_exists "$BASE" "$f"    || continue
  added=$(comm -23 \
    <(mr_show "$FWD_REF" "$f" | sed "$NORM" | grep -vE "$FILTER" | awk 'length>=10' | sort -u) \
    <(mr_show "$BASE" "$f"    | sed "$NORM" | grep -vE "$FILTER" | awk 'length>=10' | sort -u)) || true
  [ -z "$added" ] && continue
  lost=$(comm -23 <(echo "$added" | sort -u) \
    <(mr_show "$RESULT" "$f" | sed "$NORM" | grep -vE "$FILTER" | awk 'length>=10' | sort -u)) || true
  n=$(echo "$lost" | grep -c . || true)
  [ "$n" -gt 0 ] || continue
  results="${results}$(printf '%05d\t%s\n' "$n" "$f")
"
  { echo "════ $f (lost=$n) ════"; echo "$lost" | head -25; echo; } >> /tmp/_mr_detail.$$
done < /tmp/_mr_fwd.$$

echo "$results" | grep . | sort -rn | awk -F'\t' '{printf "  lost=%d  %s\n",$1,$2}'
echo "===================================================================="
echo "明细已写入 /tmp/_mr_detail.$$（本次进程）；下面打印前 60 行供初筛：" >&2
head -60 /tmp/_mr_detail.$$ 2>/dev/null || true
echo "===================================================================="
echo "务必语义核实：行级差对重构文件假阳高，多数'丢失'其实在 RESULT 改了写法/是超集。" >&2
