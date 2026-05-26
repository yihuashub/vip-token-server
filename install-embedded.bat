@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   VIP Token Server - No-Admin Installer
echo   (embedded Python; no admin rights needed)
echo ============================================
echo.

set PY_VERSION=3.12.7
set PY_TAG=python312
set PY_ZIP=python-%PY_VERSION%-embed-amd64.zip
set PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_ZIP%
set GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py

REM ---- [1/6] Download embeddable Python ----
echo [1/6] Fetching Python %PY_VERSION% embeddable (~10MB)...
if exist python\python.exe (
    echo       python\ already exists, skipping download
) else (
    if not exist "%PY_ZIP%" (
        powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"
        if errorlevel 1 goto :error
    )
    echo [2/6] Extracting to python\ ...
    powershell -NoProfile -Command "Expand-Archive -Force '%PY_ZIP%' 'python'"
    if errorlevel 1 goto :error
    del "%PY_ZIP%"
)

REM ---- [3/6] Enable site-packages by editing the ._pth ----
echo [3/6] Enabling site-packages in %PY_TAG%._pth ...
powershell -NoProfile -Command "(Get-Content 'python\%PY_TAG%._pth') -replace '^#import site', 'import site' | Set-Content 'python\%PY_TAG%._pth'"
if errorlevel 1 goto :error

REM ---- [4/6] Bootstrap pip ----
echo [4/6] Bootstrapping pip...
if exist python\Scripts\pip.exe (
    echo       pip already installed, skipping
) else (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile 'get-pip.py'"
    if errorlevel 1 goto :error
    python\python.exe get-pip.py --quiet
    if errorlevel 1 goto :error
    del get-pip.py
)

REM ---- [5/6] Install requirements ----
echo [5/6] Installing requirements (2-3 minutes, downloads from pypi.org)...
python\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :error

REM ---- [6/6] Data dir + desktop shortcut ----
echo [6/6] Creating data dir and desktop shortcut...
set DATA_DIR=%LOCALAPPDATA%\vip-token-server
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

set SHORTCUT=%USERPROFILE%\Desktop\VIP Token.lnk
set TARGET=%CD%\python\pythonw.exe
set LAUNCHER=%CD%\launch.py

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.Arguments = '\"%LAUNCHER%\"';" ^
  "$s.WorkingDirectory = '%CD%';" ^
  "$s.IconLocation = '%SystemRoot%\System32\imageres.dll,79';" ^
  "$s.Description = 'VIP Token Server (embedded Python)';" ^
  "$s.Save()"
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Done!  No admin rights were touched.
echo ============================================
echo.
echo Layout:
echo   Python      : %CD%\python\               (portable, can be deleted any time)
echo   Code        : %CD%\app\, launch.py, ...
echo   Credentials : %DATA_DIR%\credentials.json (back this up!)
echo   Shortcut    : %SHORTCUT%
echo.
echo Double-click "VIP Token" on your desktop to launch.
echo.
pause
exit /b 0

:error
echo.
echo Installation failed. See errors above.
echo If downloads were blocked, check the VM can reach python.org and pypi.org.
echo.
pause
exit /b 1
