#!/usr/bin/env bash
# build_branches.sh : 指定したブランチ群のエンジンバイナリを一括ビルドする
#
# 使い方:
#   script/ab/build_branches.sh [-e EDITION] [-a ARCH] [-c COMPILER] [-t TARGET] [-j JOBS] branch1 [branch2 ...]
#
# 例:
#   script/ab/build_branches.sh -e YANEURAOU_ENGINE_NNUE -a AVX2 \
#       claude/yaneuraou-search-optimization-qxvzz0 'claude/search-ab/*'
#
# 出力: build/ab/<ブランチ名の/を_に置換>.bin
# 各ブランチは git worktree で一時チェックアウトしてビルドする (現在の作業ツリーは汚さない)。

set -euo pipefail

EDITION=YANEURAOU_ENGINE_NNUE
ARCH=AVX2
COMPILER=clang++
TARGET=tournament
JOBS=$(nproc 2>/dev/null || echo 4)

while getopts "e:a:c:t:j:" opt; do
  case $opt in
    e) EDITION=$OPTARG ;;
    a) ARCH=$OPTARG ;;
    c) COMPILER=$OPTARG ;;
    t) TARGET=$OPTARG ;;
    j) JOBS=$OPTARG ;;
    *) echo "usage: $0 [-e edition] [-a arch] [-c compiler] [-t target] [-j jobs] branch..." >&2; exit 1 ;;
  esac
done
shift $((OPTIND-1))

[ $# -ge 1 ] || { echo "error: ブランチを1つ以上指定してください" >&2; exit 1; }

ROOT=$(git rev-parse --show-toplevel)
OUTDIR=$ROOT/build/ab
mkdir -p "$OUTDIR"

# ワイルドカード引数をブランチ名に展開
BRANCHES=()
for pat in "$@"; do
  matches=$(git -C "$ROOT" for-each-ref --format='%(refname:short)' "refs/heads/$pat" "refs/remotes/origin/$pat" | sed 's|^origin/||' | sort -u)
  if [ -n "$matches" ]; then
    while IFS= read -r b; do BRANCHES+=("$b"); done <<< "$matches"
  else
    BRANCHES+=("$pat")
  fi
done

for BR in "${BRANCHES[@]}"; do
  SAFE=${BR//\//_}
  WT=$ROOT/build/wt-$SAFE
  echo "=============================================================="
  echo "== build: $BR  ($EDITION / $ARCH / $COMPILER / $TARGET)"
  echo "=============================================================="
  git -C "$ROOT" worktree remove --force "$WT" 2>/dev/null || true
  git -C "$ROOT" worktree add --force "$WT" "$BR"
  (
    cd "$WT/source"
    make -j"$JOBS" "$TARGET" YANEURAOU_EDITION="$EDITION" TARGET_CPU="$ARCH" COMPILER="$COMPILER" >/dev/null
  )
  cp "$WT/source/YaneuraOu-by-gcc" "$OUTDIR/$SAFE.bin"
  git -C "$ROOT" worktree remove --force "$WT"
  echo "-> $OUTDIR/$SAFE.bin"
done

echo
echo "done. binaries:"
ls -l "$OUTDIR"/*.bin
