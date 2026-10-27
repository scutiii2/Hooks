@echo off
setlocal

set PY=%~dp0..\.venv\Scripts\python.exe
cd /d "%~dp0.."

if "%~1"=="" goto menu
if "%~1"=="model" goto model
if "%~1"=="skill" goto skill
goto usage

:menu
echo.
echo   1) Model router  on
echo   2) Model router  off
echo   3) Model router  status
echo   4) Skill router  on
echo   5) Skill router  off
echo   6) Skill router  status
echo.
set /p choice="Pick 1-6: "
if "%choice%"=="1" ( "%PY%" -m src.model_router.toggle on & goto end )
if "%choice%"=="2" ( "%PY%" -m src.model_router.toggle off & goto end )
if "%choice%"=="3" ( "%PY%" -m src.model_router.toggle status & goto end )
if "%choice%"=="4" ( "%PY%" -m src.skill_router.toggle on & goto end )
if "%choice%"=="5" ( "%PY%" -m src.skill_router.toggle off & goto end )
if "%choice%"=="6" ( "%PY%" -m src.skill_router.toggle status & goto end )
echo Invalid choice.
goto end

:model
if "%~2"=="" goto usage
"%PY%" -m src.model_router.toggle %~2
goto end

:skill
if "%~2"=="" goto usage
"%PY%" -m src.skill_router.toggle %~2
goto end

:usage
echo Usage: router_toggle.bat [model^|skill] [on^|off^|status]
echo    or: router_toggle.bat        (interactive menu)

:end
endlocal
pause
