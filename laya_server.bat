@echo off
setlocal

set PY=%~dp0.venv\Scripts\python.exe
cd /d "%~dp0"

if "%~1"=="start" goto start
if "%~1"=="stop" goto stop
if "%~1"=="status" goto status
if "%~1"=="autostart-on" goto autostart_on
if "%~1"=="autostart-off" goto autostart_off
if not "%~1"=="" goto usage

:menu
echo.
echo   1) Start   (waits until loaded, ~15-35 s)
echo   2) Stop    (frees ~1.6 GB RAM)
echo   3) Status
echo   4) Quit
echo   5) Autostart ON   (start the server at every login)
echo   6) Autostart OFF  (remove that login task)
echo.
set /p choice="Pick 1-6: "
if "%choice%"=="1" goto pick_start
if "%choice%"=="2" goto pick_stop
if "%choice%"=="3" goto pick_status
if "%choice%"=="4" goto end
if "%choice%"=="5" goto pick_autostart_on
if "%choice%"=="6" goto pick_autostart_off
echo Invalid choice.
goto menu

:pick_start
call :start
goto menu

:pick_stop
call :stop
goto menu

:pick_status
call :status
goto menu

:pick_autostart_on
call :autostart_on
goto menu

:pick_autostart_off
call :autostart_off
goto menu

:start
"%PY%" -m router.core.laya_server start
set /a tries=0
:wait
"%PY%" -m router.core.laya_server status >nul 2>&1 && ( echo Ready. & exit /b 0 )
set /a tries+=1
if %tries% geq 30 ( echo Not ready after 60 s. See laya_server.log, then retry. & exit /b 1 )
timeout /t 2 /nobreak >nul
goto wait

:stop
"%PY%" -m router.core.laya_server stop
exit /b

:status
"%PY%" -m router.core.laya_server status
exit /b

:autostart_on
schtasks /create /tn "ClaudeRouters Laya Server" /tr "\"%~dp0.venv\Scripts\pythonw.exe\" -m router.core.laya_server start" /sc onlogon /f
exit /b

:autostart_off
schtasks /delete /tn "ClaudeRouters Laya Server" /f
exit /b

:usage
echo Usage: laya_server.bat [start^|stop^|status^|autostart-on^|autostart-off]
echo    or: laya_server.bat        (interactive menu, loops until Quit)

:end
endlocal
