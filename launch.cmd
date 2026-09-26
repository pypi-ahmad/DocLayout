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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0doclayout\scripts\clear_gui_port.ps1"
if errorlevel 1 (
    echo Could not release port 8471. DocLayout was not launched.
    pause
    exit /b 1
)

echo Launching DocLayout at http://localhost:8471
uv run --frozen python -m streamlit run doclayout/scripts/streamlit_app.py --server.port 8471 --server.address 127.0.0.1 --server.headless false --server.fileWatcherType none
set "launcher_exit=%errorlevel%"
if not "%launcher_exit%"=="0" pause
exit /b %launcher_exit%
