@echo off
chcp 65001 >nul
title MQTT WS Serial Server

echo ============================================
echo   MQTT WebSocket Serial Transparent Server
echo ============================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Pull latest code from git
echo [1/3] Updating code from git...
git pull
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

echo Installing dependencies...
pip install -r requirements.txt -q
echo.

REM Start server
echo [3/3] Starting server...
echo ============================================
python server.py

pause
