@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   VIP Token Server - Uninstaller
echo ============================================
echo.

REM Stop the running server, if any
if exist .server.pid (
    set /p PID=<.server.pid
    echo Stopping server (PID !PID!)...
    taskkill /F /PID !PID! >nul 2>&1
    del .server.pid
) else (
    echo No running server PID file; checking port 8080 anyway...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do (
        echo Killing PID %%p on port 8080...
        taskkill /F /PID %%p >nul 2>&1
    )
)

REM Remove desktop shortcut
set SHORTCUT=%USERPROFILE%\Desktop\VIP Token.lnk
if exist "%SHORTCUT%" (
    echo Removing desktop shortcut...
    del "%SHORTCUT%"
)

echo.
echo Done. Note: the following were NOT removed (manual cleanup if you want):
if exist venv   echo   - venv\                                                 (the virtual environment from install.bat)
if exist python echo   - python\                                               (embedded Python from install-embedded.bat)
echo   - %LOCALAPPDATA%\vip-token-server\credentials.json  (your seeds — back up before deleting!)
echo.
pause
