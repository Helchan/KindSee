@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG_FILE=%CD%\logs\windows-build.log"
break > "%LOG_FILE%"

echo PyInstaller 是构建阶段第三方工具。KindEdit 的 SQL 支持需要 requirements.txt 中声明的 sqlglot 运行时依赖。
py -3.12 -m PyInstaller --noconfirm --windowed --name KindEdit --paths "%CD%\vendor" --add-data "%CD%\vendor\tkinterdnd2;vendor\tkinterdnd2" kindedit.py >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% neq 0 (
  echo 打包失败，请查看 logs\windows-build.log
  exit /b %ERRORLEVEL%
)

echo 打包完成：dist\KindEdit.exe
