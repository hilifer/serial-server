@echo off
chcp 65001 >nul
title Energy Meter API Service

echo ============================================
echo   Energy Meter API Service (COM33)
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Updating code from git...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git pull failed, continuing with current code...
)
echo.

echo [2/3] Setting up Python environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.

echo [3/3] Starting Meter API on http://0.0.0.0:8000 ...
echo   API docs: http://localhost:8000/docs
echo ============================================
python meter_api.py

pause
