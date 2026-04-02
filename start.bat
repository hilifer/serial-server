@echo off
chcp 65001 >nul
title MQTT WS Serial Server + Meter API

echo ============================================
echo   Unified Serial Server (MQTT WS + API)
echo ============================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Pull latest code from git
echo [1/3] Updating code from git...
git pull origin claude/understand-project-TBDmP
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git pull failed, continuing with current code...
)
echo.

REM Check Python and setup venv
echo [2/3] Setting up Python environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

REM Only install if marker file missing (first run or requirements changed)
if not exist "venv\.deps_installed" (
    echo Installing dependencies...
    pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    copy /y requirements.txt venv\.deps_installed >nul
    del /q venv\.deps_ok 2>nul
) else (
    fc /b requirements.txt venv\.deps_installed >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo Updating dependencies...
        pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
        copy /y requirements.txt venv\.deps_installed >nul
        del /q venv\.deps_ok 2>nul
    ) else (
        echo Dependencies up to date.
    )
)
echo.

REM Start unified server (MQTT WS bridge + Meter API)
echo [3/3] Starting unified server...
echo   Web UI: http://localhost:8000/
echo   Energy Dashboard: http://localhost:8000/detail.html
echo ============================================
python server.py

pause
