@echo off
setlocal
cd /d "%~dp0"
if /i "%~1"=="web" goto webargs
if /i "%~1"=="patch" goto patch

:menu
echo.
echo Hooks
echo.
echo   1  Web interface ^(opens http://127.0.0.1:8765/ in your browser^)
echo   2  Token economizer patch ^(Claude or Codex^)
echo   Q  Quit
echo.
choice /c 12Q /n /m "What do you want to do? "
if errorlevel 3 exit /b 0
if errorlevel 2 goto patch
goto web

rem run.bat web [--port N] passes the options on to the web page.
:webargs
set "WEBARGS="
:webloop
shift
if "%~1"=="" goto web
set "WEBARGS=%WEBARGS% %~1"
goto webloop

:web
call :ensure || exit /b 1
".venv\Scripts\python.exe" -m core.py.tools.web%WEBARGS%
exit /b %errorlevel%

rem .venv is not in git: create it on first run (needs the py launcher or python on PATH).
:ensure
if exist ".venv\Scripts\python.exe" exit /b 0
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.10+ not found. Install it from python.org, then run this again.
  exit /b 1
)
echo Creating .venv ...
%PY% -m venv .venv
if errorlevel 1 (
  echo Could not create .venv.
  exit /b 1
)
exit /b 0

:patch
call :ensure || exit /b 1
set "VPY=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0hooks\token_economizer_patch"

:p_stage1
cls
echo.
echo ===== TokenEconomizerPatch =====
echo  1  Claude
echo  2  Codex
echo  Q  Quit
echo.
choice /c 12Q /n /m "Choose: "
if errorlevel 3 exit /b 0
if errorlevel 2 ( set HOST=codex & goto p_stage2 )
set HOST=claude

:p_stage2
cls
echo.
echo ===== %HOST% =====
echo  1  Status
echo  2  Update  (update from marketplace + apply patch)
echo  3  Rebuild (uninstall, reinstall from marketplace + apply patch)
echo  4  Turn ON
echo  5  Turn OFF
echo  6  Run tests
echo  B  Back
echo.
choice /c 123456B /n /m "Choose: "
if errorlevel 7 goto p_stage1
if errorlevel 6 ( "%VPY%" -m pip install -q pytest & "%VPY%" -m pytest test_te_patch.py -q & goto p_again )
if errorlevel 5 ( "%VPY%" te_patch.py off %HOST% & goto p_again )
if errorlevel 4 ( "%VPY%" te_patch.py on %HOST% & goto p_again )
if errorlevel 3 ( "%VPY%" te_patch.py rebuild %HOST% & goto p_again )
if errorlevel 2 ( "%VPY%" te_patch.py update %HOST% & goto p_again )
"%VPY%" te_patch.py status

:p_again
pause
goto p_stage2
