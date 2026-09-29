@echo off
setlocal
cd /d "%~dp0"

if exist "dist\ReClip.exe" (
    start "" "dist\ReClip.exe"
    exit /b
)

echo ReClip.exe not found. Building it now...
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if %errorlevel% neq 0 (
    echo Build failed. Make sure Python 3.10+ is installed.
    pause
    exit /b 1
)

start "" "dist\ReClip.exe"
