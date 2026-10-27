@echo off
setlocal

set PY=%~dp0..\.venv\Scripts\python.exe
cd /d "%~dp0.."

if "%~1"=="" goto menu
if "%~1"=="add" goto run
if "%~1"=="remove" goto run
goto usage

:menu
echo Hooks Manager ================================
echo ~ Adds or removes this project's model/skill router hooks
echo ~ from a Claude Code settings.json.
echo ~ Leave directory blank to target USER settings (applies everywhere).
echo ~ template:
echo     [ADD/REMOVE] [Directory with .claude/settings.json]
echo ============================================
echo.
set /p action="ADD or REMOVE: "
set /p projdir="Directory (blank = user settings, everywhere): "

if /i "%action%"=="add" (
    if "%projdir%"=="" ( "%PY%" -m src.tools.manage_hooks add ) else ( "%PY%" -m src.tools.manage_hooks add "%projdir%\.claude\settings.json" )
    goto end
)
if /i "%action%"=="remove" (
    if "%projdir%"=="" ( "%PY%" -m src.tools.manage_hooks remove ) else ( "%PY%" -m src.tools.manage_hooks remove "%projdir%\.claude\settings.json" )
    goto end
)
echo Invalid choice: must be ADD or REMOVE.
goto end

:run
if "%~2"=="" (
    "%PY%" -m src.tools.manage_hooks %~1
) else (
    "%PY%" -m src.tools.manage_hooks %~1 "%~2\.claude\settings.json"
)
goto end

:usage
echo Hooks Manager ================================
echo ~ Adds or removes this project's model/skill router hooks
echo ~ from a Claude Code settings.json.
echo ~ No directory given targets USER settings (applies everywhere).
echo ~ template:
echo     manage_hooks.bat [ADD/REMOVE] [Directory with .claude/settings.json]
echo ============================================

:end
endlocal
pause
