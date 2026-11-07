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
".venv\Scripts\python.exe" -m core.py.tools.web%WEBARGS%
exit /b %errorlevel%

:patch
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
if errorlevel 6 ( py -m pytest test_te_patch.py -q & goto p_again )
if errorlevel 5 ( py te_patch.py off %HOST% & goto p_again )
if errorlevel 4 ( py te_patch.py on %HOST% & goto p_again )
if errorlevel 3 ( py te_patch.py rebuild %HOST% & goto p_again )
if errorlevel 2 ( py te_patch.py update %HOST% & goto p_again )
py te_patch.py status

:p_again
pause
goto p_stage2
