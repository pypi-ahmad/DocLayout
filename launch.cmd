@echo off
setlocal
title DocLayout GUI - Port 8471
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo ERROR: uv was not found on PATH.
    pause
    exit /b 1
)

echo Freeing port 8471...
powershell.exe -NoProfile -Command "try { $ErrorActionPreference = 'Stop'; $owners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8471 | Select-Object -ExpandProperty OwningProcess -Unique); foreach ($owner in $owners) { Write-Host ('Stopping process ' + $owner); Stop-Process -Id $owner -Force }; for ($attempt = 0; $attempt -lt 20; $attempt++) { $busy = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8471); if ($busy.Count -eq 0) { exit 0 }; Start-Sleep -Milliseconds 250 }; throw 'Port 8471 is still busy.' } catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
    echo Could not free port 8471. If access was denied, run this launcher as administrator.
    pause
    exit /b 1
)

echo Launching DocLayout at http://localhost:8471
uv run --frozen streamlit run doclayout/scripts/streamlit_app.py --server.port 8471 --server.address 127.0.0.1 --server.headless false --server.fileWatcherType none
set "launcher_exit=%errorlevel%"
if not "%launcher_exit%"=="0" pause
exit /b %launcher_exit%
