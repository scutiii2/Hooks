@echo off
setlocal
cd /d "%~dp0"
title Hook monitor
chcp 65001 >nul
".venv\Scripts\python.exe" -m core.py.tools.watch_decisions %*
endlocal
pause
