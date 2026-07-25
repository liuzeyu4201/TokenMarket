#!/usr/bin/env bash
# classify-blobs.sh —— blob 四点比对分类器（只读，不改仓库）
#
# 对每个文件用 BASE/OURS/THEIRS/RESULT 四点的 blob-SHA 做精确比对，分两类输出：
#
#  [A] 静默丢失·安全整取候选
#      条件：RESULT≠THEIRS 且 该文件不在 OURS 的"非 revert 真前向"集 且 THEIRS 存在该文件
#      含义：OURS 侧只通过 revert 动过它（或没动），THEIRS 版是权威；多为 revert 误删、
#            RESULT 当前缺失或被截断 → 从 THEIRS 整取可证安全。
#      注意：恢复前仍按红线判断——若整取会覆盖 RESULT 既有非空代码（而非纯补回缺失），
#            需先发用户确认（见 SKILL.md 红线/确认闸）。
#
#  [B] 行为回归候选（"问题2"）
#      条件：该文件在 OURS 真前向集 且 RESULT==THEIRS 且 RESULT≠OURS
#      含义：OURS 向前改过它，但合并结果退回了 THEIRS 旧版 → 疑似丢了 OURS 前向。
#      陷阱：若 OURS 的"前向"后来又被自己 revert 掉（净效果回退），则 RESULT 经 THEIRS
#            保留反而正确、不是回归 —— 必须逐个语义核实，勿盲改。
#
# 默认排除：敏感文件(dev.db/.env)、噪音目录(client/specs/docs…)。可用 env 覆盖
#   NOISE_RE / SENSITIVE_RE。OURS/THEIRS 由 _common.sh 自动探测，或传 incoming ref。
#
# 用法：bash classify-blobs.sh [incoming-ref]

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$DIR/_common.sh" "${1:-}"

echo "对比轴：OURS=$OURS  THEIRS=$THEIRS  BASE=$BASE  RESULT=$RESULT  (模式 $MR_MODE)" >&2

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mr_tree "$BASE"   | sort > "$TMP/base"
mr_tree "$OURS"   | sort > "$TMP/ours"
mr_tree "$THEIRS" | sort > "$TMP/theirs"
mr_tree "$RESULT" | sort > "$TMP/result"

# OURS 的"非 revert 真前向"文件集：BASE..OURS 里非 revert 主题提交触及的文件
git log "$BASE..$OURS" --name-only --pretty=format:'@@@%s' 2>/dev/null \
  | awk -v re="$REVERT_RE" '
      /^@@@/ { rev = ($0 ~ re) ? 1 : 0; next }
      NF && !rev { print }
    ' | sort -u > "$TMP/fwd_ours"

# 用 awk 合并四张 path→blob 表 + fwd 集，做分类
awk -v noise="$NOISE_RE" -v sens="$SENSITIVE_RE" '
  function blob(arr, p) { return (p in arr) ? arr[p] : "" }
  FILENAME ~ /\/base$/   { b[$1]=$2; seen[$1]; next }
  FILENAME ~ /\/ours$/   { o[$1]=$2; seen[$1]; next }
  FILENAME ~ /\/theirs$/ { t[$1]=$2; seen[$1]; next }
  FILENAME ~ /\/result$/ { r[$1]=$2; seen[$1]; next }
  FILENAME ~ /\/fwd_ours$/ { fwd[$1]=1; next }
  END {
    for (p in seen) {
      if (p ~ sens)  continue
      if (p ~ noise) continue
      ob=blob(o,p); tb=blob(t,p); rb=blob(r,p)
      isfwd = (p in fwd)
      # [A] 静默丢失·安全整取：RESULT≠THEIRS 且 非OURS前向 且 THEIRS 有
      if (rb != tb && !isfwd && tb != "")
        print "A\t" p
      # [B] 回归候选：OURS前向 且 RESULT==THEIRS 且 RESULT≠OURS
      else if (isfwd && rb == tb && rb != ob)
        print "B\t" p
    }
  }
' "$TMP/base" "$TMP/ours" "$TMP/theirs" "$TMP/result" "$TMP/fwd_ours" | sort > "$TMP/out"

a_cnt=$(awk -F'\t' '$1=="A"' "$TMP/out" | wc -l | tr -d ' ')
b_cnt=$(awk -F'\t' '$1=="B"' "$TMP/out" | wc -l | tr -d ' ')

echo "===================================================================="
echo "[A] 静默丢失·安全整取候选（共 $a_cnt）"
echo "    处置：git checkout \"$THEIRS\" -- <file>（先按红线确认是否覆盖既有代码）"
echo "    注：git checkout <tree> -- <多路径> 遇任一无效 pathspec 会整批回滚，"
echo "        先用 ls-tree 求交集剔除 THEIRS 不存在的路径。"
echo "--------------------------------------------------------------------"
awk -F'\t' '$1=="A"{print "  "$2}' "$TMP/out"
echo "===================================================================="
echo "[B] 行为回归候选（共 $b_cnt）—— 必须逐个语义核实，勿盲改"
echo "    陷阱：OURS 前向若被自己 revert 掉，则 RESULT 经 THEIRS 保留反而正确。"
echo "--------------------------------------------------------------------"
awk -F'\t' '$1=="B"{print "  "$2}' "$TMP/out"
echo "===================================================================="
echo "提示：A 类是"补回缺失"，B 类是"可能退回旧版"；任何会覆盖 RESULT 既有" >&2
echo "      非空代码的恢复/修复，按 SKILL.md 红线先发用户确认（含丢弃原因）。" >&2
