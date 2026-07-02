#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/source"

if [[ "$(uname -s)" != "Darwin" && "${ALLOW_NON_DARWIN:-0}" != "1" ]]; then
  echo "This script is intended to run on Apple Silicon macOS." >&2
  echo "Set ALLOW_NON_DARWIN=1 only if you have a working macOS cross toolchain." >&2
  exit 1
fi

MAKE_BIN="${MAKE_BIN:-}"
if [[ -z "$MAKE_BIN" ]]; then
  if command -v gmake >/dev/null 2>&1; then
    MAKE_BIN="gmake"
  else
    MAKE_BIN="make"
  fi
fi

JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 4)}"
BUILD_TARGET="${BUILD_TARGET:-tournament}"
EDITION="${YANEURAOU_EDITION:-YANEURAOU_ENGINE_SFNN1536}"
CPU="${TARGET_CPU:-APPLEM1}"
COMPILER="${COMPILER:-clang++}"
OUTPUT_NAME="${OUTPUT_NAME:-YaneuraOu-by-macos-arm64}"

if [[ "${CLEAN:-0}" == "1" ]]; then
  "$MAKE_BIN" -C "$SOURCE_DIR" clean
fi

"$MAKE_BIN" -C "$SOURCE_DIR" -j"$JOBS" "$BUILD_TARGET" \
  YANEURAOU_EDITION="$EDITION" \
  TARGET_CPU="$CPU" \
  COMPILER="$COMPILER"

cp "$SOURCE_DIR/YaneuraOu-by-gcc" "$SOURCE_DIR/$OUTPUT_NAME"
chmod +x "$SOURCE_DIR/$OUTPUT_NAME"

echo "Built: $SOURCE_DIR/$OUTPUT_NAME"
