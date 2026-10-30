@echo off
setlocal
cd /d "%~dp0"
rem run.bat              menu of hooks and tools
rem run.bat list         the short names
rem run.bat <name> ...   e.g. run.bat model_router status; a full module path (hooks.x.y) also works
".venv\Scripts\python.exe" -m core.py.tools.cli %*
exit /b %errorlevel%
