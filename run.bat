@echo off
REM Double-click to start the VIP token server.
REM Visit http://localhost:8080 in your browser.

cd /d "%~dp0"

if not exist venv (
    echo Creating venv...
    python -m venv venv || goto :error
)

if not exist venv\Lib\site-packages\fastapi (
    echo Installing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt || goto :error
)

if not exist C:\vip-data mkdir C:\vip-data

set DATA_PATH=C:\vip-data\credentials.json

echo.
echo ============================================
echo  VIP Token Server   http://localhost:8080
echo  Press Ctrl+C to stop.
echo ============================================
echo.

venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8080
goto :eof

:error
echo.
echo Setup failed. Make sure Python 3.11+ is installed and on PATH.
pause
