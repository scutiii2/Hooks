@echo off
setlocal
cd /d "%~dp0"

:stage1
cls
echo.
echo ===== TokenEconomizerPatch =====
echo  1  Claude
echo  2  Codex
echo  Q  Quit
echo.
choice /c 12Q /n /m "Choose: "
if errorlevel 3 goto :eof
if errorlevel 2 ( set HOST=codex & goto stage2 )
set HOST=claude

:stage2
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
if errorlevel 7 goto stage1
if errorlevel 6 ( py -m pytest test_te_patch.py -q & goto again )
if errorlevel 5 ( py te_patch.py off %HOST% & goto again )
if errorlevel 4 ( py te_patch.py on %HOST% & goto again )
if errorlevel 3 ( py te_patch.py rebuild %HOST% & goto again )
if errorlevel 2 ( py te_patch.py update %HOST% & goto again )
py te_patch.py status

:again
pause
goto stage2
