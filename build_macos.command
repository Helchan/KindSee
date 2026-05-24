#!/bin/zsh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

mkdir -p logs
LOG_FILE="$SCRIPT_DIR/logs/macos-build.log"
: > "$LOG_FILE"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "PyInstaller 是构建阶段第三方工具，不是 KindSee 运行时依赖。"
echo "Using Python: $PYTHON_BIN" >> "$LOG_FILE"

"$PYTHON_BIN" -m PyInstaller --noconfirm --windowed --name KindSee kindsee.py >> "$LOG_FILE" 2>&1
status=$?

if [[ $status -ne 0 ]]; then
  echo "打包失败，请查看 logs/macos-build.log"
  exit $status
fi

echo "打包完成：dist/KindSee.app"
