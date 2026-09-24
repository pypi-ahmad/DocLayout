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

echo Checking port 8471...
powershell.exe -NoProfile -Command "try { $ErrorActionPreference = 'Stop'; $busy = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8471); if ($busy.Count -ne 0) { throw 'Port 8471 is busy. Close the application using it and retry.' }; exit 0 } catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
    echo Could not use port 8471. No existing process was stopped.
    pause
    exit /b 1
)

echo Launching DocLayout at http://localhost:8471
uv run --frozen streamlit run doclayout/scripts/streamlit_app.py --server.port 8471 --server.address 127.0.0.1 --server.headless false --server.fileWatcherType none
set "launcher_exit=%errorlevel%"
if not "%launcher_exit%"=="0" pause
exit /b %launcher_exit%
