@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" goto usage
".venv\Scripts\python.exe" -m %*
exit /b %errorlevel%

:usage
echo Usage: run.bat ^<module^> [args]
echo   run.bat hooks.model_router.toggle on^|off^|status
echo   run.bat hooks.skill_router.toggle on^|off^|status
echo   run.bat core.py.tools.manage_hooks add^|remove [settings.json]
echo   run.bat core.py.tools.web [--port 8765]
echo   run.bat core.py.tools.calibrate
echo   run.bat core.py.tools.label_review model^|skill
echo   run.bat hooks.skill_router.pick "request text"
