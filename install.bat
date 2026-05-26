@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   VIP Token Server - Installer
echo ============================================
echo.

REM ---- [1/5] Python check ----
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not on PATH.
    echo Install Python 3.10 or later from https://www.python.org/downloads/
    echo During install, check "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo       Found Python !PYVER!

REM ---- [2/5] venv ----
echo [2/5] Creating virtual environment...
if exist venv (
    echo       venv already exists, skipping
) else (
    python -m venv venv
    if errorlevel 1 goto :error
)

REM ---- [3/5] Dependencies ----
echo [3/5] Installing dependencies (this may take 2-3 minutes on first run)...
venv\Scripts\python.exe -m pip install --quiet --upgrade pip
if errorlevel 1 goto :error
venv\Scripts\pip.exe install --quiet -r requirements.txt
if errorlevel 1 goto :error

REM ---- [4/5] Data directory ----
echo [4/5] Creating data directory C:\vip-data ...
if not exist C:\vip-data mkdir C:\vip-data

REM ---- [5/5] Desktop shortcut ----
echo [5/5] Creating desktop shortcut...
set SHORTCUT=%USERPROFILE%\Desktop\VIP Token.lnk
set TARGET=%CD%\venv\Scripts\pythonw.exe
set LAUNCHER=%CD%\launch.py

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.Arguments = '\"%LAUNCHER%\"';" ^
  "$s.WorkingDirectory = '%CD%';" ^
  "$s.IconLocation = '%SystemRoot%\System32\imageres.dll,79';" ^
  "$s.Description = 'VIP Token Server';" ^
  "$s.Save()"
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Done!  Look for "VIP Token" on your desktop.
echo ============================================
echo.
echo - Double-click the icon to launch.
echo - First click starts the server (~3 seconds) and opens the browser.
echo - Subsequent clicks just open the browser (server keeps running).
echo - To stop / uninstall, run uninstall.bat in this folder.
echo.
pause
exit /b 0

:error
echo.
echo Installation failed. See errors above.
echo.
pause
exit /b 1
