#!/usr/bin/env bash
# scan-markers.sh —— 标记行为扫描（只读）
#
# 找"某一侧专属行为行被合并丢掉"的回归（如 070 重设计把 desktop 的隐藏标签条件丢了）。
# 做法：对两侧都存在且与 RESULT 有差异的共享代码文件，列出
#   "目标侧(默认 THEIRS) 里命中 marker 正则、而 RESULT（去空白后）没有" 的行。
# 这些是候选——marker 行常带专属行为（isDesktopMode / executionRoute / !== 'desktop' …）。
# 命中后必须语义核实：该标识符/行为在 RESULT 是否真的完全没有（可能只是换了写法）。
#
# 用法：
#   bash scan-markers.sh [marker-regex] [side]
#     marker-regex  默认见下；可传自定义 ERE
#     side          扫描对象侧：THEIRS(默认) 或 OURS
#   incoming ref 经 env：INCOMING=<ref> bash scan-markers.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$DIR/_common.sh"

MARK="${1:-isDesktopMode|isDesktop[A-Z]|desktopMode|targetDeviceId|targetDevice|executionRoute|executionMode|redirectToBroker|openLocalFile|maybeDesktopNotify|desktopNotify|desktop_log|[\"']desktop[\"']|installationId|listenAuthCallback|reloadMainWindow|registerRunner}"
SIDE="${2:-THEIRS}"
case "$SIDE" in OURS) REF="$OURS" ;; THEIRS) REF="$THEIRS" ;; *) echo "side 须为 OURS 或 THEIRS" >&2; exit 2 ;; esac

echo "对比轴：扫描侧=$SIDE($REF)  RESULT=$RESULT  (模式 $MR_MODE)" >&2
echo "marker: $MARK" >&2
echo "===================================================================="

# 共享代码文件：扫描侧与 RESULT 都存在、且二者有差异、且属源码
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mr_tree "$REF"    | awk '{print $1}' | sort > "$TMP/side_paths"
mr_tree "$RESULT" | awk '{print $1}' | sort > "$TMP/result_paths"
comm -12 "$TMP/side_paths" "$TMP/result_paths" \
  | grep -E '^(frontend/src|backend/src|packages/[^/]+/src)' \
  | grep -vE '\.spec\.ts$|__tests__|\.snap$' > "$TMP/cands" || true

NORM='s/^[[:space:]]*//;s/[[:space:]]*$//'
hits=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # 跳过两侧完全一致的文件
  sb=$(mr_show "$REF" "$f" | git hash-object --stdin 2>/dev/null || true)
  rb=$(mr_show "$RESULT" "$f" | git hash-object --stdin 2>/dev/null || true)
  [ -n "$sb" ] && [ "$sb" = "$rb" ] && continue
  miss=$(comm -23 \
    <(mr_show "$REF" "$f"    | sed "$NORM" | grep -nE "$MARK" | sed 's/^[0-9]*://;s/^[[:space:]]*//;s/[[:space:]]*$//' | grep -vE '^//|^\*|^$' | sort -u) \
    <(mr_show "$RESULT" "$f" | sed "$NORM" | sort -u)) || true
  if [ -n "$miss" ]; then
    echo "── $f"
    echo "$miss" | sed 's/^/    ⚠ /'
    hits=$((hits+1))
  fi
done < "$TMP/cands"
echo "===================================================================="
echo "命中文件数：$hits（每条须语义核实：该行为在 RESULT 是否真缺；勿盲改）" >&2
