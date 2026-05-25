@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG_FILE=%CD%\logs\windows-launch.log"
break > "%LOG_FILE%"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3.12 -c "import sys, tkinter; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >> "%LOG_FILE%" 2>&1
  if %ERRORLEVEL%==0 (
    py -3.12 "%CD%\kindedit.py" >> "%LOG_FILE%" 2>&1
    exit /b %ERRORLEVEL%
  )
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python -c "import sys, tkinter; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >> "%LOG_FILE%" 2>&1
  if %ERRORLEVEL%==0 (
    python "%CD%\kindedit.py" >> "%LOG_FILE%" 2>&1
    exit /b %ERRORLEVEL%
  )
)

echo KindEdit 启动失败：未找到 Python 3.12 或 tkinter。>> "%LOG_FILE%"
echo KindEdit 启动失败：未找到 Python 3.12 或 tkinter。
echo 请查看 logs\windows-launch.log
pause
exit /b 1
