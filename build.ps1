$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = "C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $python -m pip install -q flask yt-dlp imageio-ffmpeg pywebview pyinstaller

Write-Host "Building ReClip desktop app..." -ForegroundColor Cyan
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "ReClip" `
    --icon "static\icon.ico" `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --add-data "tools;tools" `
    --add-data "app.py;." `
    --add-data "desktop.py;." `
    --hidden-import yt_dlp `
    --hidden-import imageio_ffmpeg `
    --hidden-import webview `
    desktop.py

Write-Host ""
Write-Host "Build complete: dist\ReClip.exe" -ForegroundColor Green
