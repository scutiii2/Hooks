@echo off
setlocal

set PY=%~dp0.venv\Scripts\python.exe
cd /d "%~dp0"
title Router decisions
chcp 65001 >nul

"%PY%" -m router.tools.watch_decisions %*

endlocal
pause
