@echo off
REM Register a new user. Usage:  register.bat alice
REM Run this once per user; it provisions a credential with Symantec and saves
REM the seed to C:\vip-data\credentials.json. The printed credential ID needs
REM to be bound on the target service (e.g. E*TRADE) once.

if "%~1"=="" (
    echo Usage: register.bat USERNAME
    exit /b 1
)

curl -sS -X POST "http://localhost:8080/users/%~1"
echo.
