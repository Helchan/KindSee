#!/bin/zsh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

mkdir -p logs
LOG_FILE="$SCRIPT_DIR/logs/macos-launch.log"
: > "$LOG_FILE"

log() {
  print -r -- "$1" >> "$LOG_FILE"
}

run_with() {
  local py="$1"
  if [[ ! -x "$py" ]]; then
    return 1
  fi
  "$py" -c "import sys, tkinter; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >> "$LOG_FILE" 2>&1 || return 1
  log "Launching with: $py"
  "$py" "$SCRIPT_DIR/kindsee.py" >> "$LOG_FILE" 2>&1
  return $?
}

candidates=(
  "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
  "/usr/local/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
  "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
  "/opt/homebrew/bin/python3.12"
  "/usr/local/bin/python3.12"
  "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
)

for py in "${candidates[@]}"; do
  run_with "$py" && exit 0
done

if command -v python3.12 >/dev/null 2>&1; then
  py="$(command -v python3.12)"
  run_with "$py" && exit 0
fi

if command -v python3 >/dev/null 2>&1; then
  py="$(command -v python3)"
  run_with "$py" && exit 0
fi

log "Python 3.12 with tkinter was not found."
osascript -e 'display alert "KindSee 启动失败" message "未找到可用的 Python 3.12 + tkinter。详情请查看 logs/macos-launch.log。"' >/dev/null 2>&1 || true
exit 1
